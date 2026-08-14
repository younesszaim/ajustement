import pytest
from app.models import (
    BatchAdjustmentItem,
    BatchCommitRequest,
    CommitRequest,
    LimonContext,
    RevertAdjustmentRequest,
    ProxyFields,
)
from app.mappings import build_mapping_provider
from app.repository import FLOW1, MockRepository
from app.services import AdjustmentService, ConflictError, DomainError


@pytest.fixture
def setup():
    repo = MockRepository()
    service = AdjustmentService(repo, build_mapping_provider())
    ctx = LimonContext(asofdate="2026-08-06", asofdateflow=FLOW1)
    return repo, service, ctx


def test_cancellation_and_immutability(setup):
    repo, s, c = setup
    original = repo.get_effective_trade(c, "ROW-0001")
    p = s.preview(c, "ROW-0001", {"amount": 1_250_000})
    assert p["cancellation"]["amount"] == -1_000_000
    assert p["cancellation"]["lcrOutflow"] == -200_000
    assert p["cancellation"]["hqlaLevel"] == "L1"
    assert original == repo.get_effective_trade(c, "ROW-0001")


def test_multiple_changes_recalculate_union(setup):
    _, s, c = setup
    p = s.preview(c, "ROW-0001", {"amount": 1_250_000, "maturityDate": "2026-11-20"})
    assert p["replacement"]["eurAmount3m"] == 1_250_000
    assert p["replacement"]["lcrOutflow"] == 250_000
    assert len(p["impactedStages"]) == len(set(p["impactedStages"]))


def test_amount_change_recalculates_the_populated_bucket(setup):
    _, service, context = setup
    preview = service.preview(context, "ROW-0001", {"amount": 1_250_000})
    assert preview["replacement"]["eurAmount30d"] == 1_250_000


def test_trade_cancellation_preview_creates_only_one_reversal(setup):
    _, service, context = setup
    preview = service.preview_cancellation(context, "ROW-0001")

    assert preview["actionType"] == "TRADE_CANCELLATION"
    assert preview["replacement"] is None
    assert len(preview["outputRows"]) == 1
    assert preview["outputRows"][0]["recordType"] == "ADJUSTMENT_CANCEL"
    assert preview["outputRows"][0]["amount"] == -1_000_000


def test_proxy_preview_generates_trade_and_calculated_output(setup):
    _, service, context = setup
    preview = service.preview_proxy(
        context,
        "12345678-1234-5678-1234-567812345678",
        ProxyFields(
            foSystem="Orchestrade",
            targetInstrumentType="SECURITY",
            isin="FRPROXY0001",
            issue="PROXY_ISSUER",
            valueDate="2026-08-06",
            maturityDate="2026-08-20",
            currency="EUR",
            amount=500_000,
            portfolio="LIQUIDITY",
            counterparty="CP_PROXY",
        ),
    )

    proxy = preview["replacement"]
    assert proxy["tradeNo"] == "PROXY-20260806-12345678"
    assert proxy["recordType"] == "PROXY"
    assert proxy["_outputRecordId"] is None
    assert proxy["eurAmount30d"] == 500_000
    assert len(preview["outputRows"]) == 1


def test_mapping_override_preserves_selected_step_and_recalculates_only_downstream(setup):
    repo, _, context = setup

    class MappingStub:
        def parameter_table(self, mapping_name):
            return build_mapping_provider().parameter_table(mapping_name)

        def validate_overrides(self, changes):
            return [
                {
                    "field": "exposureClass",
                    "value": changes["exposureClass"],
                    "selectionType": "MANUAL_MAPPING_OVERRIDE",
                    "mappingName": "exposure_class_mapping",
                    "displayName": "Exposure class",
                    "sourcePath": "s3://mock/latest/exposure.parquet",
                    "outputColumn": "EXPOSURE_CLASS",
                    "producerStage": "exposure_class",
                    "downstreamStages": ["hqla", "reporting_lines", "lcr_impacts"],
                }
            ]

    service = AdjustmentService(repo, MappingStub())
    preview = service.preview(
        context, "ROW-0001", {"exposureClass": "SOVEREIGN"}
    )

    assert preview["replacement"]["exposureClass"] == "SOVEREIGN"
    assert "exposure_class" not in preview["impactedStages"]
    assert "exposure_class" not in preview["impactedStages"]
    assert preview["impactedStages"][-3:] == ["hqla", "reporting_lines", "lcr_impacts"]
    assert preview["mappingOverrides"][0]["mappingName"] == "exposure_class_mapping"


def test_hqla_override_is_not_overwritten_by_its_producer(setup):
    repo, _, context = setup

    class MappingStub:
        def parameter_table(self, mapping_name):
            return build_mapping_provider().parameter_table(mapping_name)

        def validate_overrides(self, changes):
            return []

    preview = AdjustmentService(repo, MappingStub()).preview(
        context, "ROW-0001", {"hqlaLevel": "L2B"}
    )

    assert preview["replacement"]["hqlaLevel"] == "L2B"
    assert "hqla" not in preview["impactedStages"]
    assert "hqla" not in preview["impactedStages"]
    assert preview["impactedStages"][-2:] == ["reporting_lines", "lcr_impacts"]


def test_multiple_mapping_overrides_protect_every_selected_value(setup):
    repo, _, context = setup

    class MappingStub:
        def parameter_table(self, mapping_name):
            return build_mapping_provider().parameter_table(mapping_name)

        def validate_overrides(self, changes):
            definitions = {
                "exposureClass": ("exposure_class", ["hqla", "reporting_lines", "lcr_impacts"]),
                "hqlaLevel": ("hqla", ["reporting_lines", "lcr_impacts"]),
            }
            return [
                {
                    "field": field,
                    "value": value,
                    "selectionType": "MANUAL_MAPPING_OVERRIDE",
                    "mappingName": f"{field}_mapping",
                    "displayName": field,
                    "sourcePath": "s3://mock/latest.parquet",
                    "outputColumn": field.upper(),
                    "producerStage": definitions[field][0],
                    "downstreamStages": definitions[field][1],
                }
                for field, value in changes.items()
            ]

    preview = AdjustmentService(repo, MappingStub()).preview(
        context,
        "ROW-0001",
        {"exposureClass": "SOVEREIGN", "hqlaLevel": "L2B"},
    )

    assert preview["replacement"]["exposureClass"] == "SOVEREIGN"
    assert preview["replacement"]["hqlaLevel"] == "L2B"
    assert "exposure_class" not in preview["impactedStages"]
    assert "hqla" not in preview["impactedStages"]
    assert preview["impactedStages"][-2:] == ["reporting_lines", "lcr_impacts"]


def test_invalid_changes(setup):
    _, s, c = setup
    with pytest.raises(DomainError):
        s.preview(c, "ROW-0001", {"amount": 1_000_000})
    with pytest.raises(DomainError):
        s.preview(c, "ROW-0001", {"lcrOutflow": 999})


def test_concurrency_and_idempotency(setup):
    repo, s, c = setup
    p = s.preview(c, "ROW-0001", {"amount": 1_250_000})
    before = len(repo.get_history("ROW-0001"))
    req = CommitRequest(
        context=c,
        rowId="ROW-0001",
        changes={"amount": 1_250_000},
        reason="Finance correction",
        expectedVersion=p["rowVersion"],
        idempotencyKey="request-123",
    )
    assert s.commit(req, "tester") == s.commit(req, "tester")
    assert len(repo.get_history("ROW-0001")) == before + 1
    stale = CommitRequest(
        context=c,
        rowId="ROW-0001",
        changes={"amount": 1_500_000},
        reason="Another correction",
        expectedVersion=p["rowVersion"],
        idempotencyKey="request-456",
    )
    with pytest.raises(ConflictError):
        s.commit(stale, "tester")


def test_multi_trade_batch_is_one_commit(setup):
    repo, s, c = setup
    p1 = s.preview(c, "ROW-0001", {"amount": 1_250_000})
    p2 = s.preview(c, "ROW-0002", {"amount": 800_000})
    req = BatchCommitRequest(
        context=c,
        items=[
            BatchAdjustmentItem(
                rowId="ROW-0001",
                changes={"amount": 1_250_000},
                expectedVersion=p1["rowVersion"],
            ),
            BatchAdjustmentItem(
                rowId="ROW-0002",
                changes={"amount": 800_000},
                expectedVersion=p2["rowVersion"],
            ),
        ],
        reason="Finance batch correction",
        idempotencyKey="batch-request-123",
    )
    result = s.commit_batch(req, "tester")
    assert result["insertedRecords"] == 4
    assert result["adjustedTrades"] == 2
    assert (
        repo.get_history("ROW-0001")[0]["adjustmentBatchId"]
        == repo.get_history("ROW-0002")[0]["adjustmentBatchId"]
    )


def test_batch_preview_has_no_side_effects_and_aggregates(setup):
    repo, s, c = setup
    before1 = repo.get_effective_trade(c, "ROW-0001")
    before2 = repo.get_effective_trade(c, "ROW-0002")

    class Item:
        def __init__(self, row_id, changes):
            self.rowId = row_id
            self.changes = changes

    result = s.preview_batch(
        c,
        [
            Item("ROW-0001", {"amount": 1_250_000}),
            Item("ROW-0002", {"amount": 800_000}),
        ],
    )
    assert result["tradeCount"] == 2
    assert result["insertedRecords"] == 4
    assert any(x["field"] == "lcrOutflow" for x in result["aggregateDeltas"])
    assert repo.get_effective_trade(c, "ROW-0001") == before1
    assert repo.get_effective_trade(c, "ROW-0002") == before2


def test_adjusted_trade_lineage_marks_latest_replacement_active(setup):
    repo, _, c = setup
    lineage = repo.get_lineage(c, "ROW-0001")
    assert lineage["isAdjusted"]
    assert [x["role"] for x in lineage["rows"]] == ["ORIGINAL", "REVERSAL", "ADJUSTED"]
    assert sum(1 for x in lineage["rows"] if x["isActive"]) == 1
    assert lineage["rows"][-1]["isActive"]
    assert lineage["rows"][-1]["row"]["recordType"] == "ADJUSTMENT_REPLACEMENT"


def test_search_expands_all_associated_rows(setup):
    repo, _, c = setup
    rows, total = repo.search(c, "OT-982731", "Orchestrade", 1, 10)
    assert total == 3
    assert [x["lineageRole"] for x in rows] == ["ORIGINAL", "REVERSAL", "ADJUSTED"]
    assert [x["isActive"] for x in rows] == [False, False, True]


def test_batch_search_returns_only_filtered_effective_rows(setup):
    repo, _, context = setup

    assert "Orchestrade" in repo.fo_systems(context)
    rows, total = repo.batch_search(
        context,
        "Orchestrade",
        {"tradeNo": "OT-982731", "portfolio": "LIQ", "amountMin": 900_000},
        1,
        25,
    )

    assert total == 1
    assert [row["rowId"] for row in rows] == ["ROW-0001"]
    assert rows[0]["recordType"] == "ADJUSTMENT_REPLACEMENT"


def test_batch_search_selection_can_be_paginated(setup):
    repo, _, context = setup

    first, total = repo.batch_search(context, "Orchestrade", {}, 1, 1)
    second, _ = repo.batch_search(context, "Orchestrade", {}, 2, 1)

    assert total == 26
    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["rowId"] != second[0]["rowId"]


def test_revert_is_append_only_and_restores_prior_state(setup):
    repo, s, c = setup
    before = len(repo.get_history("ROW-0001"))
    req = RevertAdjustmentRequest(
        context=c,
        rowId="ROW-0001",
        reason="Adjustment entered in error",
        idempotencyKey="revert-request-123",
    )
    result = s.revert_adjustment("ADJ-20260807-000123", req, "controller")
    assert result["insertedRecords"] == 2
    assert len(repo.get_history("ROW-0001")) == before + 1
    event = repo.get_history("ROW-0001")[0]
    assert event["actionType"] == "REVERT"
    assert event["revertedAdjustmentBatchId"] == "ADJ-20260807-000123"
    assert repo.get_effective_trade(c, "ROW-0001")["amount"] == 900000
