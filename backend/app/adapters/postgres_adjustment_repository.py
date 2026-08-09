"""Supabase/PostgreSQL repository implementing the LiMon adjustment contract."""

from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json, os
from typing import Any
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..services import DomainError, row_version


class PostgresAdjustmentRepository:
    def __init__(self, connection_factory, project_key="limon_ldp_bmf"):
        self.connection_factory = connection_factory
        self.project_key = project_key

    @contextmanager
    def connection(self):
        conn = self.connection_factory()
        try:
            yield conn
        finally:
            conn.close()

    def _project_id(self, conn):
        row = conn.execute(
            "SELECT project_id FROM public.adjustment_projects WHERE project_key=%s AND is_active",
            (self.project_key,),
        ).fetchone()
        if not row:
            raise DomainError(
                f'Adjustment project "{self.project_key}" is not configured.'
            )
        return row["project_id"]

    @staticmethod
    def _iso(value):
        return value.isoformat() if value is not None else None

    def _domain(self, row):
        payload = deepcopy(row.get("row_payload") or {})
        payload.update(
            {
                "rowId": row["source_row_id"],
                "tradeKey": row["trade_key"],
                "tradeNo": row.get("trade_no"),
                "foSystem": row["fo_system"],
                "recordType": row["record_type"],
                "asofdate": self._iso(row["asofdate"]),
                "_outputRecordId": str(row["output_record_id"]),
                "_rowVersion": row["row_version"],
            }
        )
        for db, key in [
            ("amount", "amount"),
            ("currency", "currency"),
            ("lcr_inflow", "lcrInflow"),
            ("lcr_outflow", "lcrOutflow"),
            ("reserve_amount", "reserve"),
        ]:
            if row.get(db) is not None:
                payload[key] = (
                    float(row[db]) if isinstance(row[db], Decimal) else row[db]
                )
        return payload

    def asofdates(self):
        with self.connection() as c:
            p = self._project_id(c)
            return [
                self._iso(x["asofdate"])
                for x in c.execute(
                    "SELECT DISTINCT asofdate FROM public.out_completude_ldp_bmf WHERE project_id=%s ORDER BY asofdate DESC",
                    (p,),
                ).fetchall()
            ]

    def versions(self, date):
        with self.connection() as c:
            p = self._project_id(c)
            return [
                self._iso(x["asofdateflow"])
                for x in c.execute(
                    "SELECT DISTINCT asofdateflow FROM public.out_completude_ldp_bmf WHERE project_id=%s AND asofdate=%s ORDER BY asofdateflow DESC",
                    (p, date),
                ).fetchall()
            ]

    def search(self, context, search, fo, page, page_size):
        with self.connection() as c:
            p = self._project_id(c)
            pattern = f"%{search}%"
            offset = (page - 1) * page_size
            rows = c.execute(
                """WITH matched AS (
      SELECT source_row_id,output_record_id AS active_id,record_type AS active_type
      FROM public.v_out_completude_ldp_bmf_current
      WHERE project_id=%s AND asofdate=%s AND asofdateflow=%s AND fo_system=%s
        AND (trade_no ILIKE %s OR source_row_id ILIKE %s OR trade_key ILIKE %s OR row_payload->>'isin' ILIKE %s)
    ), expanded AS (
      SELECT o.*,m.active_id,m.active_type,count(*) OVER() AS total_count,
        count(*) FILTER (WHERE o.record_type='ADJUSTMENT_REPLACEMENT') OVER(PARTITION BY o.source_row_id) AS adjustment_count
      FROM matched m JOIN public.out_completude_ldp_bmf o USING(source_row_id)
      WHERE o.project_id=%s AND o.asofdate=%s AND o.asofdateflow=%s
    ) SELECT * FROM expanded ORDER BY source_row_id,lineage_sequence LIMIT %s OFFSET %s""",
                (
                    p,
                    context.asofdate,
                    context.asofdateflow,
                    fo,
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    p,
                    context.asofdate,
                    context.asofdateflow,
                    page_size,
                    offset,
                ),
            ).fetchall()
            result = []
            for r in rows:
                item = self._domain(r)
                role = {
                    "BASE": "ORIGINAL",
                    "ADJUSTMENT_CANCEL": "REVERSAL",
                    "ADJUSTMENT_REPLACEMENT": "ADJUSTED",
                }[r["record_type"]]
                item.update(
                    {
                        "lineageRole": role,
                        "isActive": r["output_record_id"] == r["active_id"],
                        "isAdjusted": r["adjustment_count"] > 0,
                        "adjustmentCount": r["adjustment_count"],
                        "activeRecordType": r["active_type"],
                        "adjustmentBatchId": str(r["adjustment_batch_id"])
                        if r["adjustment_batch_id"]
                        else None,
                        "lineageTimestamp": self._iso(r["created_at"]),
                    }
                )
                result.append(item)
            return result, (rows[0]["total_count"] if rows else 0)

    def _effective_db(self, conn, context, row_id):
        p = self._project_id(conn)
        row = conn.execute(
            "SELECT * FROM public.v_out_completude_ldp_bmf_current WHERE project_id=%s AND asofdate=%s AND asofdateflow=%s AND source_row_id=%s",
            (p, context.asofdate, context.asofdateflow, row_id),
        ).fetchone()
        if not row:
            raise DomainError("Trade not found in the selected LiMon version.")
        return row

    def get_effective_trade(self, context, row_id):
        with self.connection() as c:
            return self._domain(self._effective_db(c, context, row_id))

    def _history_query(self, where, args):
        with self.connection() as c:
            p = self._project_id(c)
            rows = c.execute(
                f"""SELECT b.*,b.adjustment_batch_id AS batch_id,b.created_at AS batch_created_at,b.created_by AS batch_created_by,i.source_row_id,i.trade_key,i.trade_no,i.fo_system,i.changed_fields,i.recalculated_fields,i.impacted_stages,
      oo.*,oo.row_payload AS original_payload,cc.row_payload AS cancellation_payload,rr.row_payload AS replacement_payload,
      cc.output_record_id AS cancellation_output_id,cc.record_type AS cancellation_record_type,cc.amount AS cancellation_amount,cc.lcr_inflow AS cancellation_lcr_inflow,cc.lcr_outflow AS cancellation_lcr_outflow,cc.reserve_amount AS cancellation_reserve,
      rr.output_record_id AS replacement_output_id,rr.record_type AS replacement_record_type,rr.amount AS replacement_amount,rr.lcr_inflow AS replacement_lcr_inflow,rr.lcr_outflow AS replacement_lcr_outflow,rr.reserve_amount AS replacement_reserve
    FROM public.adjustment_batches b JOIN public.adjustment_batch_items i USING(adjustment_batch_id)
    JOIN public.out_completude_ldp_bmf oo ON oo.output_record_id=i.original_record_id
    JOIN public.out_completude_ldp_bmf cc ON cc.output_record_id=i.cancellation_record_id
    JOIN public.out_completude_ldp_bmf rr ON rr.output_record_id=i.replacement_record_id
    WHERE b.project_id=%s AND {where} ORDER BY b.created_at DESC""",
                (p, *args),
            ).fetchall()
            return [self._history_domain(x) for x in rows]

    def _history_domain(self, r):
        base = dict(r)
        base["row_payload"] = r["original_payload"]
        original = self._domain(base)
        cancel = dict(base)
        cancel.update(
            {
                "row_payload": r["cancellation_payload"],
                "output_record_id": r["cancellation_output_id"],
                "record_type": r["cancellation_record_type"],
                "amount": r["cancellation_amount"],
                "lcr_inflow": r["cancellation_lcr_inflow"],
                "lcr_outflow": r["cancellation_lcr_outflow"],
                "reserve_amount": r["cancellation_reserve"],
            }
        )
        cancellation = self._domain(cancel)
        repl = dict(base)
        repl.update(
            {
                "row_payload": r["replacement_payload"],
                "output_record_id": r["replacement_output_id"],
                "record_type": r["replacement_record_type"],
                "amount": r["replacement_amount"],
                "lcr_inflow": r["replacement_lcr_inflow"],
                "lcr_outflow": r["replacement_lcr_outflow"],
                "reserve_amount": r["replacement_reserve"],
            }
        )
        replacement = self._domain(repl)
        return {
            "adjustmentBatchId": str(r["batch_id"]),
            "status": r["status"],
            "actionType": r["action_type"],
            "revertedAdjustmentBatchId": str(r["reverted_adjustment_batch_id"])
            if r["reverted_adjustment_batch_id"]
            else None,
            "timestamp": self._iso(r["batch_created_at"]),
            "user": r["batch_created_by"],
            "reason": r["reason"],
            "baseAsOfDate": self._iso(r["base_asofdate"]),
            "baseAsOfDateFlow": self._iso(r["base_asofdateflow"]),
            "changedFields": r["changed_fields"],
            "recalculatedFields": r["recalculated_fields"],
            "original": original,
            "cancellation": cancellation,
            "replacement": replacement,
        }

    def get_history(self, row_id):
        return self._history_query("i.source_row_id=%s", (row_id,))

    def get_global_history(self, asofdate="", asofdateflow=""):
        clauses = ["TRUE"]
        args = []
        if asofdate:
            clauses.append("b.base_asofdate=%s")
            args.append(asofdate)
        if asofdateflow:
            clauses.append("b.base_asofdateflow=%s")
            args.append(asofdateflow)
        return self._history_query(" AND ".join(clauses), tuple(args))

    def get_idempotent(self, key):
        with self.connection() as c:
            p = self._project_id(c)
            row = c.execute(
                "SELECT adjustment_batch_id,status,inserted_record_count,trade_count FROM public.adjustment_batches WHERE project_id=%s AND idempotency_key=%s",
                (p, key),
            ).fetchone()
            return (
                {
                    "adjustmentBatchId": str(row["adjustment_batch_id"]),
                    "status": row["status"],
                    "insertedRecords": row["inserted_record_count"],
                    "adjustedTrades": row["trade_count"],
                }
                if row
                else None
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
        with self.connection() as c:
            with c.transaction():
                p = self._project_id(c)
                c.execute(
                    """INSERT INTO public.adjustment_action_events(project_id,source_row_id,event_type,event_status,actor_user_id,asofdate,asofdateflow,event_metadata)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        p,
                        source_row_id,
                        event_type,
                        status,
                        user,
                        getattr(context, "asofdate", None),
                        getattr(context, "asofdateflow", None),
                        Jsonb(metadata),
                    ),
                )

    def get_adjustment(self, row_id, batch_id, context):
        entries = [
            x
            for x in self.get_history(row_id)
            if x["baseAsOfDate"] == context.asofdate.isoformat()
            and x["baseAsOfDateFlow"] == context.asofdateflow.isoformat()
        ]
        target = next((x for x in entries if x["adjustmentBatchId"] == batch_id), None)
        if not target:
            raise DomainError("Adjustment not found for this trade and LiMon version.")
        if entries[0]["adjustmentBatchId"] != batch_id:
            raise DomainError(
                "Only the latest active adjustment can be reverted. Revert newer adjustments first."
            )
        if target.get("actionType") == "REVERT":
            raise DomainError(
                "A revert record cannot be reverted as a deletion action."
            )
        return target

    def get_lineage(self, context, row_id):
        current = self.get_effective_trade(context, row_id)
        entries = [
            x
            for x in self.get_history(row_id)
            if x["baseAsOfDate"] == context.asofdate.isoformat()
            and x["baseAsOfDateFlow"] == context.asofdateflow.isoformat()
        ]
        if not entries:
            return {
                "isAdjusted": False,
                "adjustmentCount": 0,
                "activeRow": current,
                "rows": [
                    {
                        "role": "ORIGINAL",
                        "isActive": True,
                        "adjustmentBatchId": None,
                        "timestamp": None,
                        "row": current,
                    }
                ],
            }
        chronological = sorted(entries, key=lambda x: x["timestamp"])
        rows = [
            {
                "role": "ORIGINAL",
                "isActive": False,
                "adjustmentBatchId": None,
                "timestamp": None,
                "row": chronological[0]["original"],
            }
        ]
        for e in chronological:
            rows.extend(
                [
                    {
                        "role": "REVERSAL",
                        "isActive": False,
                        "adjustmentBatchId": e["adjustmentBatchId"],
                        "timestamp": e["timestamp"],
                        "row": e["cancellation"],
                    },
                    {
                        "role": "ADJUSTED",
                        "isActive": False,
                        "adjustmentBatchId": e["adjustmentBatchId"],
                        "timestamp": e["timestamp"],
                        "row": e["replacement"],
                    },
                ]
            )
        rows[-1]["isActive"] = True
        return {
            "isAdjusted": True,
            "adjustmentCount": len(entries),
            "activeRow": current,
            "rows": rows,
        }

    def _insert_output(
        self, c, p, context, row, batch_id, parent_id, original_id, user
    ):
        payload = {
            k: v
            for k, v in row.items()
            if not k.startswith("_")
            and k
            not in {
                "rowId",
                "tradeKey",
                "tradeNo",
                "foSystem",
                "recordType",
                "asofdate",
            }
        }
        version = row_version(row)
        return c.execute(
            """INSERT INTO public.out_completude_ldp_bmf(project_id,asofdate,asofdateflow,source_row_id,trade_key,trade_no,fo_system,record_type,adjustment_batch_id,parent_record_id,original_record_id,row_version,row_payload,amount,currency,lcr_inflow,lcr_outflow,reserve_amount,created_by)
   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING output_record_id""",
            (
                p,
                context.asofdate,
                context.asofdateflow,
                row["rowId"],
                row["tradeKey"],
                row.get("tradeNo"),
                row["foSystem"],
                row["recordType"],
                batch_id,
                parent_id,
                original_id,
                version,
                Jsonb(payload),
                row.get("amount"),
                row.get("currency"),
                row.get("lcrInflow"),
                row.get("lcrOutflow"),
                row.get("reserve"),
                user,
            ),
        ).fetchone()["output_record_id"]

    def commit_adjustment(self, built, reason, user, key):
        return self.commit_adjustment_batch([built], reason, user, key)

    def commit_adjustment_batch(self, built_items, reason, user, key):
        with self.connection() as c:
            with c.transaction():
                p = self._project_id(c)
                existing = c.execute(
                    "SELECT adjustment_batch_id,status,inserted_record_count,trade_count FROM public.adjustment_batches WHERE project_id=%s AND idempotency_key=%s",
                    (p, key),
                ).fetchone()
                if existing:
                    return {
                        "adjustmentBatchId": str(existing["adjustment_batch_id"]),
                        "status": existing["status"],
                        "insertedRecords": existing["inserted_record_count"],
                        "adjustedTrades": existing["trade_count"],
                    }
                now = datetime.now(timezone.utc)
                reference = f"ADJ-{now:%Y%m%d}-{now:%H%M%S%f}"
                first = built_items[0]
                revert = first.get("revertedAdjustmentBatchId")
                batch = c.execute(
                    """INSERT INTO public.adjustment_batches(project_id,batch_reference,action_type,status,base_asofdate,base_asofdateflow,reason,created_by,reverted_adjustment_batch_id,idempotency_key,trade_count,inserted_record_count)
      VALUES(%s,%s,%s,'COMMITTED',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING adjustment_batch_id""",
                    (
                        p,
                        reference,
                        first.get("actionType", "ADJUSTMENT"),
                        first["context"].asofdate,
                        first["context"].asofdateflow,
                        reason,
                        user,
                        revert,
                        key,
                        len(built_items),
                        len(built_items) * 2,
                    ),
                ).fetchone()["adjustment_batch_id"]
                for built in built_items:
                    current = self._effective_db(
                        c, built["context"], built["original"]["rowId"]
                    )
                    parent = current["output_record_id"]
                    original = current["original_record_id"] or parent
                    cancel_id = self._insert_output(
                        c,
                        p,
                        built["context"],
                        built["cancellation"],
                        batch,
                        parent,
                        original,
                        user,
                    )
                    replacement_id = self._insert_output(
                        c,
                        p,
                        built["context"],
                        built["replacement"],
                        batch,
                        parent,
                        original,
                        user,
                    )
                    item = c.execute(
                        """INSERT INTO public.adjustment_batch_items(adjustment_batch_id,source_row_id,trade_key,trade_no,fo_system,expected_row_version,original_record_id,cancellation_record_id,replacement_record_id,changed_fields,recalculated_fields,impacted_stages)
       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING adjustment_item_id""",
                        (
                            batch,
                            current["source_row_id"],
                            current["trade_key"],
                            current["trade_no"],
                            current["fo_system"],
                            built.get("rowVersion", current["row_version"]),
                            parent,
                            cancel_id,
                            replacement_id,
                            Jsonb(built["changedFields"]),
                            Jsonb(built["recalculatedFields"]),
                            Jsonb(built.get("impactedStages", [])),
                        ),
                    ).fetchone()["adjustment_item_id"]
                    for change in built["changedFields"]:
                        c.execute(
                            "INSERT INTO public.adjustment_field_changes(adjustment_item_id,field_name,old_value,new_value,value_type,is_recalculated) VALUES(%s,%s,%s,%s,%s,false)",
                            (
                                item,
                                change["field"],
                                Jsonb(change.get("oldValue")),
                                Jsonb(change.get("newValue")),
                                type(change.get("newValue")).__name__,
                            ),
                        )
                c.execute(
                    """INSERT INTO public.adjustment_action_events(project_id,adjustment_batch_id,event_type,actor_user_id,asofdate,asofdateflow,event_metadata)
      VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        p,
                        batch,
                        "ADJUSTMENT_REVERTED"
                        if revert
                        else (
                            "BATCH_COMMITTED"
                            if len(built_items) > 1
                            else "ADJUSTMENT_COMMITTED"
                        ),
                        user,
                        first["context"].asofdate,
                        first["context"].asofdateflow,
                        Jsonb(
                            {
                                "tradeCount": len(built_items),
                                "insertedRecords": len(built_items) * 2,
                            }
                        ),
                    ),
                )
            return {
                "adjustmentBatchId": str(batch),
                "status": "COMMITTED",
                "insertedRecords": len(built_items) * 2,
                "adjustedTrades": len(built_items),
            }


def connection_from_environment():
    import psycopg

    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL is required when USE_MOCK_DATA=false")
    return psycopg.connect(url, connect_timeout=10, row_factory=dict_row)
