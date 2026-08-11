from datetime import date, datetime

import pytest

from app.adapters.hybrid_adjustment_repository import HybridAdjustmentRepository
from app.models import LimonContext
from app.services import InfrastructureError


class OutputStub:
    def __init__(self, rows):
        self.rows = rows

    def get_rows_by_batch_reference(self, reference):
        assert reference == "ADJ-pending"
        return self.rows


class AuditStub:
    def __init__(self):
        self.marked = None
        self.finalized = None

    def get_recovery_request_by_batch_reference(self, project, reference):
        assert project == "limon_ldp_bmf"
        assert reference == "ADJ-pending"
        return {
            "requestId": "request-1",
            "batchReference": reference,
            "actionType": "ADJUSTMENT",
            "reason": "Correction",
            "user": "tester",
            "revertedAdjustmentBatchId": None,
            "items": [
                {
                    "context": LimonContext(
                        asofdate=date(2026, 8, 7),
                        asofdateflow=datetime(2026, 8, 7, 10, 0),
                    ),
                    "cancellation": {"recordType": "ADJUSTMENT_CANCEL"},
                    "replacement": {"recordType": "ADJUSTMENT_REPLACEMENT"},
                }
            ],
        }

    def mark_vertica_committed(self, request_id, external_ids):
        self.marked = (request_id, external_ids)

    def finalize_request(self, request_id, batch, items):
        self.finalized = (request_id, batch, items)
        return {
            "adjustmentBatchId": "batch-1",
            "status": "COMMITTED",
            "insertedRecords": 2,
            "adjustedTrades": 1,
        }


def test_reconciliation_uses_existing_output_rows_and_finalizes_metadata():
    output = OutputStub(
        [{"_outputRecordId": "cancel-1"}, {"_outputRecordId": "replacement-1"}]
    )
    audit = AuditStub()
    repo = HybridAdjustmentRepository(output, audit)

    result = repo.reconcile_adjustment("ADJ-pending")

    assert result["status"] == "COMMITTED"
    assert audit.marked == ("request-1", ["cancel-1", "replacement-1"])
    assert audit.finalized[0] == "request-1"


def test_reconciliation_blocks_partial_output_batches():
    repo = HybridAdjustmentRepository(
        OutputStub([{"_outputRecordId": "cancel-1"}]), AuditStub()
    )

    with pytest.raises(InfrastructureError, match="manual investigation"):
        repo.reconcile_adjustment("ADJ-pending")
