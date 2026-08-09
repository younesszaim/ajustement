"""PostgreSQL metadata boundary for hybrid Vertica/PostgreSQL deployments.

The concrete SQL methods are intentionally small and schema-driven so another
adjustment project can reuse them with a different project_key.
"""

from datetime import datetime, timezone
from psycopg.types.json import Jsonb
from ..services import DomainError


class PostgresAuditRepository:
    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def reserve_request(
        self,
        project_key,
        key,
        context,
        user,
        reason,
        item_count,
        action_type="ADJUSTMENT",
        reverted_batch_id=None,
    ):
        with self.connection_factory() as c:
            row = c.execute(
                """INSERT INTO public.adjustment_requests(project_id,idempotency_key,batch_reference,action_type,base_asofdate,base_asofdateflow,reason,requested_by,item_count,reverted_adjustment_batch_id)
    SELECT project_id,%s,%s,%s,%s,%s,%s,%s,%s,%s FROM public.adjustment_projects WHERE project_key=%s
    ON CONFLICT(project_id,idempotency_key) DO UPDATE SET idempotency_key=EXCLUDED.idempotency_key
    RETURNING request_id,batch_reference,status""",
                (
                    key,
                    f"ADJ-{datetime.now(timezone.utc):%Y%m%d-%H%M%S%f}",
                    action_type,
                    context.asofdate,
                    context.asofdateflow,
                    reason,
                    user,
                    item_count,
                    reverted_batch_id,
                    project_key,
                ),
            ).fetchone()
            return {
                "requestId": str(row["request_id"]),
                "batchReference": row["batch_reference"],
                "status": row["status"],
            }

    def mark_vertica_committed(self, request_id, external_ids):
        with self.connection_factory() as c:
            c.execute(
                "UPDATE public.adjustment_requests SET status='VERTICA_COMMITTED',vertica_record_ids=%s,updated_at=now() WHERE request_id=%s",
                (external_ids, request_id),
            )

    def mark_request_failed(self, request_id, error_code, error_message):
        with self.connection_factory() as c:
            c.execute(
                "UPDATE public.adjustment_requests SET status='FAILED',error_code=%s,error_message=%s,updated_at=now() WHERE request_id=%s",
                (error_code, error_message[:2000], request_id),
            )

    def get_idempotent_result(self, project_key, key):
        with self.connection_factory() as c:
            r = c.execute(
                """SELECT r.status,r.batch_reference,b.adjustment_batch_id,b.inserted_record_count,b.trade_count FROM public.adjustment_requests r LEFT JOIN public.adjustment_batches b ON b.batch_reference=r.batch_reference AND b.project_id=r.project_id JOIN public.adjustment_projects p USING(project_id) WHERE p.project_key=%s AND r.idempotency_key=%s""",
                (project_key, key),
            ).fetchone()
            if not r:
                return None
            if r["status"] != "COMMITTED":
                raise DomainError(f"Adjustment request is currently {r['status']}.")
            return {
                "adjustmentBatchId": str(r["adjustment_batch_id"]),
                "status": "COMMITTED",
                "insertedRecords": r["inserted_record_count"],
                "adjustedTrades": r["trade_count"],
            }

    def finalize_request(self, request_id, batch, items):
        raise NotImplementedError(
            "Map item snapshots and external Vertica record IDs using migration 003 and the enterprise audit conventions."
        )

    def get_history(self, project_key, row_id):
        raise NotImplementedError(
            "Implement with adjustment_item_snapshots for hybrid mode."
        )

    def get_global_history(self, project_key, asofdate="", asofdateflow=""):
        raise NotImplementedError(
            "Implement with adjustment_item_snapshots for hybrid mode."
        )

    def get_latest_revertible(self, project_key, row_id, batch_id, context):
        raise NotImplementedError(
            "Resolve the latest committed snapshot from PostgreSQL audit metadata."
        )

    def record_action(
        self,
        event_type,
        user,
        metadata,
        context=None,
        source_row_id=None,
        status="SUCCESS",
    ):
        with self.connection_factory() as c:
            c.execute(
                """INSERT INTO public.adjustment_action_events(project_id,source_row_id,event_type,event_status,actor_user_id,asofdate,asofdateflow,event_metadata) SELECT project_id,%s,%s,%s,%s,%s,%s,%s FROM public.adjustment_projects WHERE project_key=%s""",
                (
                    source_row_id,
                    event_type,
                    status,
                    user,
                    getattr(context, "asofdate", None),
                    getattr(context, "asofdateflow", None),
                    Jsonb(metadata),
                    "limon_ldp_bmf",
                ),
            )
