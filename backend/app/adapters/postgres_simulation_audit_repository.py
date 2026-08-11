"""PostgreSQL metadata repository for the two-schema hybrid simulator."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from ..services import DomainError, row_version
from ..models import LimonContext


class PostgresSimulationAuditRepository:
    def __init__(self, connection_factory, schema="adjustment_meta"):
        self.connection_factory = connection_factory
        self.schema = schema

    @contextmanager
    def connection(self):
        connection = self.connection_factory()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _project_id(self, connection, project_key):
        row = connection.execute(
            f"SELECT project_id FROM {self.schema}.projects WHERE project_key=%s AND is_active",
            (project_key,),
        ).fetchone()
        if not row:
            raise DomainError(f'Adjustment project "{project_key}" is not configured.')
        return row["project_id"]

    @staticmethod
    def _iso(value):
        return value.isoformat() if value is not None else None

    def health(self):
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT
                    (SELECT count(*) FROM {self.schema}.requests) AS requests,
                    (SELECT count(*) FROM {self.schema}.batches) AS batches,
                    (SELECT count(*) FROM {self.schema}.item_snapshots) AS snapshots"""
            ).fetchone()
            return {
                "schema": self.schema,
                "requests": row["requests"],
                "batches": row["batches"],
                "snapshots": row["snapshots"],
            }

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
        with self.connection() as connection:
            with connection.transaction():
                project_id = self._project_id(connection, project_key)
                prefix = {
                    "REVERT": "REV",
                    "TRADE_CANCELLATION": "CAN",
                    "PROXY": "PRX",
                }.get(action_type, "ADJ")
                reference = f"{prefix}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S%f}"
                row = connection.execute(
                    f"""INSERT INTO {self.schema}.requests(
                        project_id,idempotency_key,batch_reference,action_type,base_asofdate,base_asofdateflow,
                        reason,requested_by,item_count,reverted_adjustment_batch_id)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(project_id,idempotency_key) DO UPDATE SET updated_at=now()
                        RETURNING request_id,batch_reference,status""",
                    (
                        project_id,key,reference,action_type,context.asofdate,context.asofdateflow,
                        reason,user,item_count,reverted_batch_id,
                    ),
                ).fetchone()
                return {
                    "requestId": str(row["request_id"]),
                    "batchReference": row["batch_reference"],
                    "status": row["status"],
                }

    def mark_vertica_committed(self, request_id, external_ids):
        with self.connection() as connection:
            connection.execute(
                f"""UPDATE {self.schema}.requests
                    SET status='OUTPUT_COMMITTED',output_record_ids=%s,error_code=NULL,error_message=NULL,updated_at=now()
                    WHERE request_id=%s""",
                (external_ids, request_id),
            )

    @staticmethod
    def _serializable_item(item):
        return {
            key: (
                {
                    "asofdate": value.asofdate.isoformat(),
                    "asofdateflow": value.asofdateflow.isoformat(),
                }
                if key == "context"
                else value
            )
            for key, value in item.items()
        }

    def stage_request(self, request_id, items):
        payload = [self._serializable_item(item) for item in items]
        with self.connection() as connection:
            connection.execute(
                f"UPDATE {self.schema}.requests SET request_payload=%s,updated_at=now() WHERE request_id=%s",
                (Jsonb(payload), request_id),
            )

    def get_recovery_request(self, project_key, key):
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT r.* FROM {self.schema}.requests r
                    JOIN {self.schema}.projects p USING(project_id)
                    WHERE p.project_key=%s AND r.idempotency_key=%s""",
                (project_key, key),
            ).fetchone()
            return self._recovery_domain(row)

    def get_recovery_request_by_batch_reference(self, project_key, reference):
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT r.* FROM {self.schema}.requests r
                    JOIN {self.schema}.projects p USING(project_id)
                    WHERE p.project_key=%s AND r.batch_reference=%s""",
                (project_key, reference),
            ).fetchone()
            return self._recovery_domain(row)

    @staticmethod
    def _recovery_domain(row):
        if not row or row["status"] == "COMMITTED" or not row["request_payload"]:
            return None
        items = list(row["request_payload"])
        for item in items:
            item["context"] = LimonContext(**item["context"])
        return {
            "requestId": str(row["request_id"]),
            "batchReference": row["batch_reference"],
            "actionType": row["action_type"],
            "reason": row["reason"],
            "user": row["requested_by"],
            "revertedAdjustmentBatchId": str(row["reverted_adjustment_batch_id"])
            if row["reverted_adjustment_batch_id"] else None,
            "items": items,
        }

    def mark_request_failed(self, request_id, error_code, error_message, reconciliation=False):
        with self.connection() as connection:
            connection.execute(
                f"""UPDATE {self.schema}.requests SET status=%s,error_code=%s,error_message=%s,updated_at=now()
                    WHERE request_id=%s AND status<>'COMMITTED'""",
                (
                    "RECONCILIATION_REQUIRED" if reconciliation else "FAILED",
                    error_code,
                    error_message[:2000],
                    request_id,
                ),
            )

    def get_idempotent_result(self, project_key, key):
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT r.status,b.adjustment_batch_id,b.inserted_record_count,b.trade_count
                    FROM {self.schema}.requests r
                    JOIN {self.schema}.projects p USING(project_id)
                    LEFT JOIN {self.schema}.batches b
                      ON b.project_id=r.project_id AND b.batch_reference=r.batch_reference
                    WHERE p.project_key=%s AND r.idempotency_key=%s""",
                (project_key, key),
            ).fetchone()
            if not row or row["status"] != "COMMITTED":
                return None
            return {
                "adjustmentBatchId": str(row["adjustment_batch_id"]),
                "status": "COMMITTED",
                "insertedRecords": row["inserted_record_count"],
                "adjustedTrades": row["trade_count"],
            }

    def finalize_request(self, request_id, batch, items):
        with self.connection() as connection:
            with connection.transaction():
                request = connection.execute(
                    f"SELECT * FROM {self.schema}.requests WHERE request_id=%s FOR UPDATE",
                    (request_id,),
                ).fetchone()
                if not request:
                    raise DomainError("Reserved adjustment request was not found.")
                existing = connection.execute(
                    f"SELECT * FROM {self.schema}.batches WHERE project_id=%s AND batch_reference=%s",
                    (request["project_id"], request["batch_reference"]),
                ).fetchone()
                if existing:
                    connection.execute(
                        f"UPDATE {self.schema}.requests SET status='COMMITTED',updated_at=now() WHERE request_id=%s",
                        (request_id,),
                    )
                    return self._result(existing)

                output_ids = list(request["output_record_ids"] or [])
                expected_count = sum(
                    len(item.get("outputRows") or self._legacy_output_rows(item))
                    for item in items
                )
                if len(output_ids) != expected_count:
                    raise DomainError("Output record count does not match the reserved batch.")
                batch_row = connection.execute(
                    f"""INSERT INTO {self.schema}.batches(
                        project_id,batch_reference,action_type,base_asofdate,base_asofdateflow,reason,created_by,
                        reverted_adjustment_batch_id,idempotency_key,trade_count,inserted_record_count)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (
                        request["project_id"],request["batch_reference"],batch["actionType"],
                        batch["context"].asofdate,batch["context"].asofdateflow,batch["reason"],batch["user"],
                        batch.get("revertedAdjustmentBatchId"),request["idempotency_key"],len(items),len(output_ids),
                    ),
                ).fetchone()
                output_offset = 0
                for built in items:
                    original = built.get("original")
                    cancellation = built.get("cancellation")
                    replacement = built.get("replacement")
                    item_rows = built.get("outputRows") or self._legacy_output_rows(built)
                    item_ids = output_ids[output_offset : output_offset + len(item_rows)]
                    output_offset += len(item_rows)
                    id_by_type = {
                        row["recordType"]: output_id
                        for row, output_id in zip(item_rows, item_ids)
                    }
                    source = original or replacement
                    snapshot = connection.execute(
                        f"""INSERT INTO {self.schema}.item_snapshots(
                            adjustment_batch_id,source_output_record_id,parent_output_record_id,
                            cancellation_output_record_id,replacement_output_record_id,trade_no,fo_system,
                            expected_row_version,original_snapshot,cancellation_snapshot,replacement_snapshot,
                            changed_fields,recalculated_fields,impacted_stages)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING snapshot_id""",
                        (
                            batch_row["adjustment_batch_id"],source["rowId"],
                            original.get("_outputRecordId") if original else None,
                            id_by_type.get("ADJUSTMENT_CANCEL"),
                            id_by_type.get("ADJUSTMENT_REPLACEMENT") or id_by_type.get("PROXY"),
                            source.get("tradeNo"),source.get("foSystem"),
                            built.get("rowVersion",row_version(source)),
                            Jsonb(original) if original else None,
                            Jsonb(cancellation) if cancellation else None,
                            Jsonb(replacement) if replacement else None,
                            Jsonb(built["changedFields"]),Jsonb(built["recalculatedFields"]),
                            Jsonb(built.get("impactedStages", [])),
                        ),
                    ).fetchone()
                    for change in built["changedFields"]:
                        connection.execute(
                            f"""INSERT INTO {self.schema}.field_changes(
                                snapshot_id,field_name,old_value,new_value,value_type)
                                VALUES(%s,%s,%s,%s,%s)""",
                            (
                                snapshot["snapshot_id"],change["field"],Jsonb(change.get("oldValue")),
                                Jsonb(change.get("newValue")),type(change.get("newValue")).__name__,
                            ),
                        )
                event_type = {
                    "REVERT": "ADJUSTMENT_REVERTED",
                    "TRADE_CANCELLATION": "TRADE_CANCELLED",
                    "PROXY": "PROXY_CREATED",
                }.get(
                    batch["actionType"],
                    "BATCH_COMMITTED" if len(items) > 1 else "ADJUSTMENT_COMMITTED",
                )
                connection.execute(
                    f"""INSERT INTO {self.schema}.action_events(
                        project_id,adjustment_batch_id,event_type,actor_user_id,asofdate,asofdateflow,event_metadata)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        request["project_id"],batch_row["adjustment_batch_id"],event_type,batch["user"],
                        batch["context"].asofdate,batch["context"].asofdateflow,
                        Jsonb({"tradeCount": len(items), "insertedRecords": len(output_ids)}),
                    ),
                )
                connection.execute(
                    f"UPDATE {self.schema}.requests SET status='COMMITTED',updated_at=now() WHERE request_id=%s",
                    (request_id,),
                )
                return self._result(batch_row)

    @staticmethod
    def _legacy_output_rows(item):
        return [
            row
            for row in (item.get("cancellation"), item.get("replacement"))
            if row is not None
        ]

    @staticmethod
    def _result(row):
        return {
            "adjustmentBatchId": str(row["adjustment_batch_id"]),
            "status": "COMMITTED",
            "insertedRecords": row["inserted_record_count"],
            "adjustedTrades": row["trade_count"],
        }

    def _history(self, project_key, where="TRUE", args=()):
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT b.*,s.* FROM {self.schema}.batches b
                    JOIN {self.schema}.projects p USING(project_id)
                    JOIN {self.schema}.item_snapshots s USING(adjustment_batch_id)
                    WHERE p.project_key=%s AND {where}
                    ORDER BY b.created_at DESC""",
                (project_key, *args),
            ).fetchall()
            return [self._history_domain(row) for row in rows]

    def _history_domain(self, row):
        return {
            "adjustmentBatchId": str(row["adjustment_batch_id"]),
            "status": row["status"],
            "actionType": row["action_type"],
            "revertedAdjustmentBatchId": str(row["reverted_adjustment_batch_id"])
            if row["reverted_adjustment_batch_id"] else None,
            "timestamp": self._iso(row["created_at"]),
            "user": row["created_by"],
            "reason": row["reason"],
            "baseAsOfDate": self._iso(row["base_asofdate"]),
            "baseAsOfDateFlow": self._iso(row["base_asofdateflow"]),
            "changedFields": row["changed_fields"],
            "recalculatedFields": row["recalculated_fields"],
            "original": row["original_snapshot"],
            "cancellation": row["cancellation_snapshot"],
            "replacement": row["replacement_snapshot"],
        }

    def get_history(self, project_key, row_id):
        committed = self._history(
            project_key, "s.source_output_record_id=%s", (row_id,)
        )
        pending = self._pending_history(project_key, row_id=row_id)
        return sorted(
            committed + pending, key=lambda item: item["timestamp"], reverse=True
        )

    def get_global_history(self, project_key, asofdate="", asofdateflow=""):
        clauses, args = ["TRUE"], []
        if asofdate:
            clauses.append("b.base_asofdate=%s")
            args.append(asofdate)
        if asofdateflow:
            clauses.append("b.base_asofdateflow=%s")
            args.append(asofdateflow)
        committed = self._history(
            project_key, " AND ".join(clauses), tuple(args)
        )
        pending = self._pending_history(
            project_key, asofdate=asofdate, asofdateflow=asofdateflow
        )
        return sorted(
            committed + pending, key=lambda item: item["timestamp"], reverse=True
        )

    def _pending_history(
        self, project_key, row_id=None, asofdate="", asofdateflow=""
    ):
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT r.* FROM {self.schema}.requests r
                    JOIN {self.schema}.projects p USING(project_id)
                    WHERE p.project_key=%s AND r.status<>'COMMITTED'
                      AND jsonb_array_length(r.request_payload)>0
                    ORDER BY r.created_at DESC""",
                (project_key,),
            ).fetchall()
        result = []
        for request in rows:
            if asofdate and self._iso(request["base_asofdate"]) != asofdate:
                continue
            if (
                asofdateflow
                and self._iso(request["base_asofdateflow"]) != asofdateflow
            ):
                continue
            for item in request["request_payload"]:
                original = item.get("original")
                source = original or item.get("replacement")
                if not source or (row_id and source["rowId"] != row_id):
                    continue
                result.append(
                    {
                        "adjustmentBatchId": request["batch_reference"],
                        "status": request["status"],
                        "actionType": request["action_type"],
                        "revertedAdjustmentBatchId": str(
                            request["reverted_adjustment_batch_id"]
                        )
                        if request["reverted_adjustment_batch_id"]
                        else None,
                        "timestamp": self._iso(request["created_at"]),
                        "user": request["requested_by"],
                        "reason": request["reason"],
                        "baseAsOfDate": self._iso(request["base_asofdate"]),
                        "baseAsOfDateFlow": self._iso(
                            request["base_asofdateflow"]
                        ),
                        "changedFields": item["changedFields"],
                        "recalculatedFields": item["recalculatedFields"],
                        "original": original,
                        "cancellation": item["cancellation"],
                        "replacement": item["replacement"],
                    }
                )
        return result

    def get_latest_revertible(self, project_key, row_id, batch_id, context):
        entries = [
            item for item in self.get_history(project_key, row_id)
            if item["baseAsOfDate"] == context.asofdate.isoformat()
            and item["baseAsOfDateFlow"] == context.asofdateflow.isoformat()
        ]
        target = next((item for item in entries if item["adjustmentBatchId"] == batch_id), None)
        if not target:
            raise DomainError("Adjustment not found for this trade and LiMon version.")
        if entries[0]["adjustmentBatchId"] != batch_id:
            raise DomainError("Only the latest active adjustment can be reverted.")
        if target["actionType"] == "REVERT":
            raise DomainError("A revert record cannot be reverted as a deletion action.")
        return target

    def record_action(
        self,event_type,user,metadata,context=None,source_row_id=None,status="SUCCESS",project_key="limon_ldp_bmf"
    ):
        with self.connection() as connection:
            project_id = self._project_id(connection, project_key)
            connection.execute(
                f"""INSERT INTO {self.schema}.action_events(
                    project_id,source_output_record_id,event_type,event_status,actor_user_id,asofdate,asofdateflow,event_metadata)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    project_id,source_row_id,event_type,status,user,getattr(context,"asofdate",None),
                    getattr(context,"asofdateflow",None),Jsonb(metadata),
                ),
            )
