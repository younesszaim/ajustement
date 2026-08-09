import pytest
from app.models import (
    BatchAdjustmentItem,
    BatchCommitRequest,
    CommitRequest,
    LimonContext,
    RevertAdjustmentRequest,
)
from app.repository import FLOW1, MockRepository
from app.services import AdjustmentService, ConflictError, DomainError


@pytest.fixture
def setup():
    repo = MockRepository()
    service = AdjustmentService(repo)
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


def test_invalid_changes(setup):
    _, s, c = setup
    with pytest.raises(DomainError):
        s.preview(c, "ROW-0001", {"amount": 1_000_000})
    with pytest.raises(DomainError):
        s.preview(c, "ROW-0001", {"hqlaLevel": "L2"})


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
