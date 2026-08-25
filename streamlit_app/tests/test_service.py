from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pytest

from streamlit_app.config import load_settings
from streamlit_app.models import AdjustmentDraft, Context
from streamlit_app.service import AdjustmentError, AdjustmentService


class FakeOutput:
    def __init__(self, row):
        self.row = row
        self.rows = []
        self.by_id = {row["bi_id"]: deepcopy(row)}

    def get_active(self, output_id):
        return deepcopy(self.row) if output_id == self.row["bi_id"] else None

    def get_by_id(self, output_id):
        value = self.by_id.get(output_id)
        return deepcopy(value) if value else None

    def reference_exists(self, reference):
        return any(row["adjustment_reference"] == reference for row in self.rows)

    def append(self, rows):
        self.rows.extend(deepcopy(rows))


class FailingOutput(FakeOutput):
    """Simulate a transactional output failure before any row is committed."""

    def append(self, rows):
        raise ValueError("simulated Vertica VARCHAR failure")


class FakeOperations:
    def __init__(self):
        self.operations = {}

    def find_by_key(self, key):
        return deepcopy(self.operations.get(key))

    def create(self, operation):
        self.operations[operation["idempotency_key"]] = {
            **deepcopy(operation),
            "status": "PENDING",
            "output_ids": None,
            "error_message": None,
        }

    def set_status(self, operation_id, status, output_ids=None, error_message=None):
        operation = next(value for value in self.operations.values() if value["operation_id"] == operation_id)
        operation.update(status=status, output_ids=output_ids, error_message=error_message)

    def get_operation(self, operation_id):
        value = next(
            (value for value in self.operations.values() if value["operation_id"] == operation_id),
            None,
        )
        return deepcopy(value)

    def commit_revert(self, revert_operation_id, target_operation_id, output_ids):
        revert = next(value for value in self.operations.values() if value["operation_id"] == revert_operation_id)
        target = next(value for value in self.operations.values() if value["operation_id"] == target_operation_id)
        revert.update(status="COMMITTED", output_ids=output_ids, error_message=None)
        target["status"] = "REVERTED"


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://unused")
    return load_settings(Path(__file__).parents[1] / "project.yaml")


@pytest.fixture
def base_row():
    return {
        "bi_id": "ROW-1",
        "AsOfDate": "2026-08-06",
        "AsOfDateFlow": "2026-08-07T11:14:09",
        "FOSystem": "Murex",
        "TradeNo": "T-100",
        "isin_code": "FR0000000001",
        "security_leg_flag": 0,
        "Cash_Amount_EUR": 100.0,
        "SecurityAmount_EUR": 0.0,
        "MaturityDate": "2026-08-12",
        "eur_amount_7d": 100.0,
        "eur_amount_30d": 0.0,
        "eur_amount_3m": 0.0,
        "ldp_impact_asset": 0.0,
        "ldp_impact_asset_cash_gestion": 100.0,
        "ldp_impact_lcr_reglementaire": 100.0,
        "record_type": "BASE",
        "adjustment_reference": None,
        "source_output_record_id": None,
        "parent_output_record_id": None,
        "BusinessColumnNotDisplayed": "preserved",
    }


def test_cash_preview_builds_reversal_and_recalculated_adjusted_row(settings, base_row):
    service = AdjustmentService(FakeOutput(base_row), FakeOperations(), settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Correct cash amount", "intent-1")

    preview = service.preview(context, draft)

    assert preview.original["Cash_Amount_EUR"] == 100.0
    assert preview.reversal["Cash_Amount_EUR"] == -100.0
    assert preview.reversal["record_type"] == "REVERSAL"
    assert preview.adjusted["Cash_Amount_EUR"] == 250.0
    assert preview.adjusted["eur_amount_7d"] == 250.0
    assert preview.adjusted["record_type"] == "ADJUSTED"
    assert preview.reversal["parent_output_record_id"] == "ROW-1"
    assert preview.adjusted["BusinessColumnNotDisplayed"] == "preserved"


def test_commit_retry_does_not_append_duplicate_output(settings, base_row):
    output, operations = FakeOutput(base_row), FakeOperations()
    service = AdjustmentService(output, operations, settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Correct cash amount", "intent-1")

    first = service.commit(context, draft)
    second = service.commit(context, draft)

    assert first["status"] == second["status"] == "COMMITTED"
    assert len(output.rows) == 2
    assert operations.operations["intent-1"]["output_ids"] == ["REV-intent-1", "ADJ-intent-1"]


def test_committed_key_rejects_changed_draft_instead_of_returning_old_success(settings, base_row):
    output, operations = FakeOutput(base_row), FakeOperations()
    service = AdjustmentService(output, operations, settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    original = AdjustmentDraft("ROW-1", 250.0, "First intention", "intent-1")

    service.commit(context, original)
    changed = AdjustmentDraft(
        "ROW-1", 250.0, "First intention", "intent-1",
        changes={"exposure_class": "CORPORATE"},
    )

    with pytest.raises(AdjustmentError, match="different adjustment intention"):
        service.commit(context, changed)
    assert len(output.rows) == 2


def test_failed_key_rejects_changed_reason_and_context(settings, base_row):
    output, operations = FakeOutput(base_row), FakeOperations()
    service = AdjustmentService(output, operations, settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Original reason", "intent-1")
    operations.create({
        "operation_id": "operation-1", "idempotency_key": "intent-1",
        "operation_type": "REPLACE", "asofdate": context.asofdate,
        "version": context.version, "fo_system": context.fo_system,
        "leg_flag": context.leg_flag, "source_output_id": draft.source_output_id,
        "reason": draft.reason, "created_by": "limon-user",
        "payload": {"changes": service._requested_changes(context.leg_flag, draft)},
    })
    operations.operations["intent-1"]["status"] = "FAILED"

    with pytest.raises(AdjustmentError, match="reason"):
        service.commit(
            context,
            AdjustmentDraft("ROW-1", 250.0, "Changed reason", "intent-1"),
        )
    with pytest.raises(AdjustmentError, match="fo_system"):
        service.commit(
            Context("2026-08-06", "2026-08-07T11:14:09", "Other", 0), draft
        )


def test_output_failure_marks_operation_failed_and_same_draft_can_retry(settings, base_row):
    operations = FakeOperations()
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Correct amount", "intent-failed")
    failing_service = AdjustmentService(FailingOutput(base_row), operations, settings)

    with pytest.raises(AdjustmentError, match="output write failed"):
        failing_service.commit(context, draft)

    assert operations.operations["intent-failed"]["status"] == "FAILED"
    assert operations.operations["intent-failed"]["output_ids"] is None

    # The infrastructure problem is now fixed. Reusing the exact same draft
    # and key resumes the existing operation instead of creating a duplicate.
    recovered_output = FakeOutput(base_row)
    recovered_service = AdjustmentService(recovered_output, operations, settings)
    result = recovered_service.commit(context, draft)

    assert result["status"] == "COMMITTED"
    assert len(recovered_output.rows) == 2


def test_retry_repairs_postgres_after_output_was_already_written(settings, base_row):
    output, operations = FakeOutput(base_row), FakeOperations()
    operations.operations["intent-1"] = {
        "operation_id": "operation-1",
        "status": "PENDING",
        "payload": {"new_amount": 250.0},
        "output_ids": None,
        "error_message": None,
    }
    output.rows = [{"adjustment_reference": "intent-1"}]
    service = AdjustmentService(output, operations, settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Correct cash amount", "intent-1")

    result = service.commit(context, draft)

    assert result["status"] == "COMMITTED"
    assert len(output.rows) == 1
    assert operations.operations["intent-1"]["status"] == "COMMITTED"


def test_preview_rejects_row_outside_selected_context(settings, base_row):
    service = AdjustmentService(FakeOutput(base_row), FakeOperations(), settings)
    wrong_context = Context("2026-08-06", "another-version", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Reason", "intent-1")

    with pytest.raises(AdjustmentError, match="current context"):
        service.preview(wrong_context, draft)


def test_preview_accepts_equivalent_database_and_json_datetime_formats(settings, base_row):
    base_row["AsOfDate"] = date(2026, 8, 6)
    base_row["AsOfDateFlow"] = datetime(2026, 8, 7, 11, 14, 9)
    service = AdjustmentService(FakeOutput(base_row), FakeOperations(), settings)
    json_context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft("ROW-1", 250.0, "Reason", "intent-1")

    preview = service.preview(json_context, draft)

    assert preview.adjusted["Cash_Amount_EUR"] == 250.0


def test_preview_applies_controlled_exposure_and_reporting_line_changes(settings, base_row):
    base_row["exposure_class"] = "RETAIL"
    base_row["reporting_line_lcr"] = "RL_DEP_01"
    service = AdjustmentService(FakeOutput(base_row), FakeOperations(), settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft(
        "ROW-1",
        100.0,
        "Correct classification",
        "intent-fields",
        changes={"exposure_class": "CORPORATE", "reporting_line_lcr": "RL_LOAN_01"},
    )

    preview = service.preview(context, draft)

    assert preview.original["exposure_class"] == "RETAIL"
    assert preview.adjusted["exposure_class"] == "CORPORATE"
    assert preview.adjusted["reporting_line_lcr"] == "RL_LOAN_01"


def test_preview_rejects_value_outside_configured_options(settings, base_row):
    service = AdjustmentService(FakeOutput(base_row), FakeOperations(), settings)
    context = Context("2026-08-06", "2026-08-07T11:14:09", "Murex", 0)
    draft = AdjustmentDraft(
        "ROW-1", 100.0, "Invalid", "intent-invalid", changes={"exposure_class": "UNKNOWN"}
    )

    with pytest.raises(AdjustmentError, match="not allowed"):
        service.preview(context, draft)


def test_revert_appends_negative_adjusted_row_and_restores_original(settings, base_row):
    adjusted = deepcopy(base_row)
    adjusted.update(
        bi_id="ADJ-first",
        Cash_Amount_EUR=250.0,
        eur_amount_7d=250.0,
        ldp_impact_asset_cash_gestion=250.0,
        ldp_impact_lcr_reglementaire=250.0,
        record_type="ADJUSTED",
        adjustment_reference="first",
        source_output_record_id="ROW-1",
        parent_output_record_id="ROW-1",
    )
    output = FakeOutput(adjusted)
    output.by_id["ROW-1"] = deepcopy(base_row)
    operations = FakeOperations()
    operations.operations["first"] = {
        "operation_id": "operation-first",
        "idempotency_key": "first",
        "operation_type": "REPLACE",
        "status": "COMMITTED",
        "asofdate": "2026-08-06",
        "version": "2026-08-07T11:14:09",
        "fo_system": "Murex",
        "leg_flag": 0,
        "source_output_id": "ROW-1",
        "reason": "First adjustment",
        "created_by": "limon-user",
        "payload": {"changes": {"cash_amount_eur": 250.0}},
        "output_ids": ["REV-first", "ADJ-first"],
        "error_message": None,
    }
    service = AdjustmentService(output, operations, settings)

    result = service.revert("operation-first", "Undo incorrect adjustment", "revert-1")

    assert result["status"] == "COMMITTED"
    assert len(output.rows) == 2
    reversal, restored = output.rows
    assert reversal["Cash_Amount_EUR"] == -250.0
    assert reversal["parent_output_record_id"] == "ADJ-first"
    assert restored["Cash_Amount_EUR"] == 100.0
    assert restored["bi_id"] == "ADJ-revert-1"
    assert operations.operations["first"]["status"] == "REVERTED"
    assert operations.operations["revert-1"]["status"] == "COMMITTED"

    with pytest.raises(AdjustmentError, match="already been reverted"):
        service.revert("operation-first", "Try twice", "revert-2")
