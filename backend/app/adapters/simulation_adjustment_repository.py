"""Coordinates immutable Vertica output rows with PostgreSQL audit metadata.

There is no cross-database ACID transaction between Vertica and PostgreSQL.
This coordinator uses a durable PostgreSQL request plus an idempotent Vertica
batch reference. A recovery worker can safely finish a request after a crash.
"""

from __future__ import annotations
import os
from ..services import InfrastructureError


class SimulationAdjustmentRepository:
    """Facade over independent output and audit repositories.

    Commit methods reserve durable metadata first, write output using a stable
    batch reference, then finalize metadata. A failure after output commit is
    recoverable because reconciliation can locate those output rows by the same
    reference instead of inserting them again.
    """
    def __init__(
        self,
        output_repository,
        audit_repository,
        project_key="limon_ldp_bmf",
    ):
        self.output = output_repository
        self.audit = audit_repository
        self.project_key = project_key

    def health(self):
        return {
            "output": self.output.health() if hasattr(self.output, "health") else None,
            "metadata": self.audit.health() if hasattr(self.audit, "health") else None,
        }

    def asofdates(self):
        return self.output.asofdates()

    def versions(self, date):
        return self.output.versions(date)

    def search(self, *args):
        return self.output.search(*args)

    def fo_systems(self, *args):
        return self.output.fo_systems(*args)

    def batch_search(self, *args):
        return self.output.batch_search(*args)

    def get_effective_trade(self, *args):
        return self.output.get_effective_trade(*args)

    def get_trade_detail(self, *args):
        if hasattr(self.output, "get_trade_detail"):
            return self.output.get_trade_detail(*args)
        return self.output.get_effective_trade(*args)

    def get_lineage(self, *args):
        return self.output.get_lineage(*args)

    def get_history(self, row_id):
        return self.audit.get_history(self.project_key, row_id)

    def get_global_history(self, asofdate="", asofdateflow=""):
        return self.audit.get_global_history(self.project_key, asofdate, asofdateflow)

    def get_idempotent(self, key):
        completed = self.audit.get_idempotent_result(self.project_key, key)
        if completed:
            return completed
        if not hasattr(self.audit, "get_recovery_request"):
            return None
        recovery = self.audit.get_recovery_request(self.project_key, key)
        if not recovery:
            return None
        external_rows = self.output.get_rows_by_batch_reference(
            recovery["batchReference"]
        )
        if not external_rows:
            return None
        expected_count = sum(
            len(item.get("outputRows") or self._legacy_output_rows(item))
            for item in recovery["items"]
        )
        if len(external_rows) != expected_count:
            raise RuntimeError(
                "Output contains a partial adjustment batch; reconciliation is required."
            )
        external_ids = [row["_outputRecordId"] for row in external_rows]
        self.audit.mark_vertica_committed(recovery["requestId"], external_ids)
        return self.audit.finalize_request(
            recovery["requestId"],
            {
                "actionType": recovery["actionType"],
                "reason": recovery["reason"],
                "user": recovery["user"],
                "context": recovery["items"][0]["context"],
                "revertedAdjustmentBatchId": recovery[
                    "revertedAdjustmentBatchId"
                ],
            },
            recovery["items"],
        )

    def record_action(self, *args, **kwargs):
        kwargs.setdefault("project_key", self.project_key)
        try:
            return self.audit.record_action(*args, **kwargs)
        except TypeError:
            kwargs.pop("project_key", None)
            return self.audit.record_action(*args, **kwargs)

    def get_adjustment(self, row_id, batch_id, context):
        return self.audit.get_latest_revertible(
            self.project_key, row_id, batch_id, context
        )

    def reconcile_adjustment(self, batch_reference):
        """Finalize metadata for output rows already committed externally.

        Reconciliation is idempotent: it locates rows using the stable batch
        reference and never inserts them again. Once metadata is complete,
        history and business revert become available normally.
        """
        if not hasattr(self.audit, "get_recovery_request_by_batch_reference"):
            raise InfrastructureError(
                "This audit repository does not support interactive reconciliation."
            )
        recovery = self.audit.get_recovery_request_by_batch_reference(
            self.project_key, batch_reference
        )
        if not recovery:
            raise InfrastructureError(
                "No incomplete adjustment request was found for this batch reference."
            )
        external_rows = self.output.get_rows_by_batch_reference(batch_reference)
        expected_count = sum(
            len(item.get("outputRows") or self._legacy_output_rows(item))
            for item in recovery["items"]
        )
        if len(external_rows) != expected_count:
            raise InfrastructureError(
                "Automatic reconciliation stopped: "
                f"expected {expected_count} output rows but found {len(external_rows)}. "
                "The batch requires manual investigation."
            )
        external_ids = [row["_outputRecordId"] for row in external_rows]
        try:
            self.audit.mark_vertica_committed(recovery["requestId"], external_ids)
            return self.audit.finalize_request(
                recovery["requestId"],
                {
                    "actionType": recovery["actionType"],
                    "reason": recovery["reason"],
                    "user": recovery["user"],
                    "context": recovery["items"][0]["context"],
                    "revertedAdjustmentBatchId": recovery[
                        "revertedAdjustmentBatchId"
                    ],
                },
                recovery["items"],
            )
        except Exception as exc:
            self.audit.mark_request_failed(
                recovery["requestId"],
                type(exc).__name__,
                str(exc),
                reconciliation=True,
            )
            raise InfrastructureError(
                "The output rows are intact, but audit reconciliation failed. "
                "You can safely retry reconciliation."
            ) from exc

    def commit_adjustment(self, built, reason, user, key):
        """Commit one standard journal through the shared batch coordinator."""
        return self.commit_adjustment_batch([built], reason, user, key)

    def commit_adjustment_batch(self, built_items, reason, user, key):
        """Coordinate one logical business commit across output and metadata.

        The idempotency key is reserved before the output write. If metadata
        finalization later fails, the durable request and batch reference are
        sufficient for ``reconcile_adjustment`` to finish safely.
        """
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
        external_ids = []
        try:
            if hasattr(self.audit, "stage_request"):
                self.audit.stage_request(request["requestId"], built_items)
            self._inject_failure("AFTER_REQUEST_RESERVED")
            rows = []
            for built in built_items:
                rows.extend(
                    built.get("outputRows") or self._legacy_output_rows(built)
                )
            external_ids = self.output.insert_adjustment_rows(
                first["context"], reference, rows, user
            )
            self._inject_failure("AFTER_OUTPUT_COMMITTED")
            self.audit.mark_vertica_committed(request["requestId"], external_ids)
            self._inject_failure("AFTER_OUTPUT_STATUS_RECORDED")
            self._inject_failure("BEFORE_METADATA_FINALIZED")
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
                request["requestId"],
                type(exc).__name__,
                str(exc),
                reconciliation=bool(external_ids),
            )
            raise

    @staticmethod
    def _legacy_output_rows(item):
        return [
            row
            for row in (item.get("cancellation"), item.get("replacement"))
            if row is not None
        ]

    @staticmethod
    def _inject_failure(point):
        if os.getenv("SIMULATED_FAILURE_POINT") == point:
            raise InfrastructureError(
                f"Simulated infrastructure failure at {point}. Retry the same request after restarting without failure injection."
            )
