"""Coordinates immutable Vertica output rows with PostgreSQL audit metadata.

There is no cross-database ACID transaction between Vertica and PostgreSQL.
This coordinator uses a durable PostgreSQL request plus an idempotent Vertica
batch reference. A recovery worker can safely finish a request after a crash.
"""

from __future__ import annotations
from .postgres_audit_repository import PostgresAuditRepository


class HybridAdjustmentRepository:
    def __init__(
        self,
        output_repository,
        audit_repository: PostgresAuditRepository,
        project_key="limon_ldp_bmf",
    ):
        self.output = output_repository
        self.audit = audit_repository
        self.project_key = project_key

    def asofdates(self):
        return self.output.asofdates()

    def versions(self, date):
        return self.output.versions(date)

    def search(self, *args):
        return self.output.search(*args)

    def get_effective_trade(self, *args):
        return self.output.get_effective_trade(*args)

    def get_lineage(self, *args):
        return self.output.get_lineage(*args)

    def get_history(self, row_id):
        return self.audit.get_history(self.project_key, row_id)

    def get_global_history(self, asofdate="", asofdateflow=""):
        return self.audit.get_global_history(self.project_key, asofdate, asofdateflow)

    def get_idempotent(self, key):
        return self.audit.get_idempotent_result(self.project_key, key)

    def record_action(self, *args, **kwargs):
        return self.audit.record_action(*args, **kwargs)

    def get_adjustment(self, row_id, batch_id, context):
        return self.audit.get_latest_revertible(
            self.project_key, row_id, batch_id, context
        )

    def commit_adjustment(self, built, reason, user, key):
        return self.commit_adjustment_batch([built], reason, user, key)

    def commit_adjustment_batch(self, built_items, reason, user, key):
        existing = self.get_idempotent(key)
        if existing:
            return existing
        first = built_items[0]
        action = first.get("actionType", "ADJUSTMENT")
        reverted = first.get("revertedAdjustmentBatchId")
        request = self.audit.reserve_request(
            self.project_key,
            key,
            first["context"],
            user,
            reason,
            len(built_items),
            action,
            reverted,
        )
        reference = request["batchReference"]
        try:
            rows = []
            for built in built_items:
                rows.extend([built["cancellation"], built["replacement"]])
            external_ids = self.output.insert_adjustment_rows(
                first["context"], reference, rows, user
            )
            self.audit.mark_vertica_committed(request["requestId"], external_ids)
            return self.audit.finalize_request(
                request["requestId"],
                {
                    "actionType": action,
                    "reason": reason,
                    "user": user,
                    "context": first["context"],
                    "revertedAdjustmentBatchId": reverted,
                },
                built_items,
            )
        except Exception as exc:
            self.audit.mark_request_failed(
                request["requestId"], type(exc).__name__, str(exc)
            )
            raise
