"""PostgreSQL-backed simulation of the real Vertica output boundary.

The adapter deliberately owns a separate connection and transaction from the
metadata repository. No SQL statement joins the two schemas.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from ..services import DomainError


class PostgresVerticaSimulatorRepository:
    def __init__(self, connection_factory, schema="vertica_sim"):
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

    @staticmethod
    def _iso(value):
        return value.isoformat() if value is not None else None

    @staticmethod
    def _number(value):
        return float(value) if isinstance(value, Decimal) else value

    def health(self):
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT
                    (SELECT count(*) FROM {self.schema}.output_completude_table) AS output_rows,
                    (SELECT count(*) FROM {self.schema}.output_adjustment_links) AS adjustment_links"""
            ).fetchone()
            return {
                "schema": self.schema,
                "outputRows": row["output_rows"],
                "adjustmentLinks": row["adjustment_links"],
            }

    def _domain(self, row):
        source_id = row.get("source_output_record_id") or row["output_record_id"]
        return {
            "rowId": source_id,
            "tradeKey": "|".join(
                str(row.get(key) or "")
                for key in ("fo_system", "trade_no", "isin", "portfolio")
            ),
            "tradeNo": row["trade_no"],
            "foSystem": row["fo_system"],
            "targetInstrumentType": row.get("target_instrument_type"),
            "isin": row.get("isin"),
            "issue": row.get("issue"),
            "valueDate": self._iso(row.get("value_date")),
            "maturityDate": self._iso(row.get("maturity_date")),
            "currency": row.get("currency"),
            "amount": self._number(row.get("amount")),
            "portfolio": row.get("portfolio"),
            "counterparty": row.get("counterparty"),
            "exposureClass": row.get("exposure_class"),
            "hqlaLevel": row.get("hqla_level"),
            "reportingLineLcr": row.get("reporting_line_lcr"),
            "eurAmount0d": self._number(row.get("eur_amount_0d")),
            "eurAmount7d": self._number(row.get("eur_amount_7d")),
            "eurAmount30d": self._number(row.get("eur_amount_30d")),
            "eurAmount3m": self._number(row.get("eur_amount_3m")),
            "lcrInflow": self._number(row.get("lcr_inflow")),
            "lcrOutflow": self._number(row.get("lcr_outflow")),
            "reserve": self._number(row.get("reserve_amount")),
            "recordType": row["record_type"],
            "asofdate": self._iso(row["asofdate"]),
            "adjustmentReference": row.get("adjustment_reference"),
            "_outputRecordId": row["output_record_id"],
            "_parentOutputRecordId": row.get("parent_output_record_id"),
            "_createdAt": self._iso(row.get("created_at")),
        }

    def asofdates(self):
        with self.connection() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT asofdate FROM {self.schema}.output_completude_table ORDER BY asofdate DESC"
            ).fetchall()
            return [self._iso(row["asofdate"]) for row in rows]

    def versions(self, asofdate):
        with self.connection() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT asofdateflow FROM {self.schema}.output_completude_table WHERE asofdate=%s ORDER BY asofdateflow DESC",
                (asofdate,),
            ).fetchall()
            return [self._iso(row["asofdateflow"]) for row in rows]

    def _context_rows(self, connection, context):
        return connection.execute(
            f"""SELECT o.*,l.source_output_record_id,l.parent_output_record_id,l.item_position
                FROM {self.schema}.output_completude_table o
                LEFT JOIN {self.schema}.output_adjustment_links l USING(output_record_id)
                WHERE o.asofdate=%s AND o.asofdateflow=%s
                ORDER BY o.created_at,o.output_record_id""",
            (context.asofdate, context.asofdateflow),
        ).fetchall()

    @staticmethod
    def _group_rows(rows):
        grouped = {}
        for row in rows:
            source = row.get("source_output_record_id") or row["output_record_id"]
            grouped.setdefault(source, []).append(row)
        return grouped

    @staticmethod
    def _active(rows):
        ranked = {
            "BASE": 0,
            "ADJUSTMENT_CANCEL": 1,
            "ADJUSTMENT_REPLACEMENT": 2,
            "PROXY": 2,
        }
        latest = max(
            rows,
            key=lambda row: (
                row["created_at"],
                row.get("adjustment_reference") or "",
                ranked[row["record_type"]],
            ),
        )
        return None if latest["record_type"] == "ADJUSTMENT_CANCEL" else latest

    def search(self, context, search, fo_system, page, page_size):
        with self.connection() as connection:
            grouped = self._group_rows(self._context_rows(connection, context))
        needle = search.casefold()
        matches = []
        for source_id, rows in grouped.items():
            active = self._active(rows)
            display = active or max(rows, key=lambda row: row["created_at"])
            if fo_system and display["fo_system"] != fo_system:
                continue
            searchable = (display["trade_no"], display.get("isin"), source_id)
            if needle and not any(needle in str(value or "").casefold() for value in searchable):
                continue
            matches.append((source_id, rows, active, display))
        matches.sort(key=lambda item: (item[3]["trade_no"], item[0]))
        expanded = []
        for _, rows, active, _ in matches:
            replacement_count = sum(
                row["record_type"] == "ADJUSTMENT_REPLACEMENT" for row in rows
            )
            for row in rows:
                item = self._domain(row)
                item.update(
                    {
                        "lineageRole": {
                            "BASE": "ORIGINAL",
                            "ADJUSTMENT_CANCEL": "REVERSAL",
                            "ADJUSTMENT_REPLACEMENT": "ADJUSTED",
                            "PROXY": "PROXY",
                        }[row["record_type"]],
                        "isActive": bool(active) and row["output_record_id"] == active["output_record_id"],
                        "isAdjusted": replacement_count > 0,
                        "adjustmentCount": replacement_count,
                        "activeRecordType": active["record_type"] if active else "CANCELLED",
                        "adjustmentBatchId": row.get("adjustment_reference"),
                        "lineageTimestamp": self._iso(row.get("created_at")),
                    }
                )
                expanded.append(item)
        start = (page - 1) * page_size
        return expanded[start : start + page_size], len(expanded)

    def _lineage_rows(self, connection, context, row_id):
        rows = self._context_rows(connection, context)
        return self._group_rows(rows).get(row_id, [])

    def get_effective_trade(self, context, row_id):
        with self.connection() as connection:
            rows = self._lineage_rows(connection, context, row_id)
        if not rows:
            raise DomainError("Trade not found in the selected LiMon version.")
        active = self._active(rows)
        if not active:
            raise DomainError("This trade is cancelled and has no active business row.")
        return self._domain(active)

    def get_lineage(self, context, row_id):
        with self.connection() as connection:
            rows = self._lineage_rows(connection, context, row_id)
        if not rows:
            raise DomainError("Trade not found in the selected LiMon version.")
        active = self._active(rows)
        result = []
        for row in rows:
            result.append(
                {
                    "role": {
                        "BASE": "ORIGINAL",
                        "ADJUSTMENT_CANCEL": "REVERSAL",
                        "ADJUSTMENT_REPLACEMENT": "ADJUSTED",
                        "PROXY": "PROXY",
                    }[row["record_type"]],
                    "isActive": bool(active) and row["output_record_id"] == active["output_record_id"],
                    "adjustmentBatchId": row.get("adjustment_reference"),
                    "timestamp": self._iso(row.get("created_at")),
                    "row": self._domain(row),
                }
            )
        return {
            "isAdjusted": any(row["record_type"] != "BASE" for row in rows),
            "adjustmentCount": sum(
                row["record_type"] == "ADJUSTMENT_REPLACEMENT" for row in rows
            ),
            "activeRow": self._domain(active) if active else None,
            "rows": result,
        }

    def get_rows_by_batch_reference(self, batch_reference):
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT o.*,l.source_output_record_id,l.parent_output_record_id,l.item_position
                    FROM {self.schema}.output_adjustment_links l
                    JOIN {self.schema}.output_completude_table o USING(output_record_id)
                    WHERE l.adjustment_reference=%s
                    ORDER BY l.item_position,CASE l.record_type WHEN 'ADJUSTMENT_CANCEL' THEN 0 ELSE 1 END""",
                (batch_reference,),
            ).fetchall()
            return [self._domain(row) for row in rows]

    @staticmethod
    def _output_id(batch_reference, source_id, record_type):
        return str(uuid5(NAMESPACE_URL, f"{batch_reference}|{source_id}|{record_type}"))

    def insert_adjustment_rows(self, context, batch_reference, rows, user):
        with self.connection() as connection:
            with connection.transaction():
                existing = connection.execute(
                    f"""SELECT output_record_id FROM {self.schema}.output_adjustment_links
                        WHERE adjustment_reference=%s
                        ORDER BY item_position,CASE record_type WHEN 'ADJUSTMENT_CANCEL' THEN 0 ELSE 1 END""",
                    (batch_reference,),
                ).fetchall()
                if existing:
                    if len(existing) != len(rows):
                        raise DomainError(
                            "Output contains a partial adjustment batch; reconciliation is required."
                        )
                    return [row["output_record_id"] for row in existing]

                output_ids = []
                for position, row in enumerate(rows):
                    source_id = row["rowId"]
                    parent_id = row.get("_outputRecordId")
                    record_type = row["recordType"]
                    output_id = self._output_id(batch_reference, source_id, record_type)
                    output_ids.append(output_id)
                    connection.execute(
                        f"""INSERT INTO {self.schema}.output_completude_table(
                            output_record_id,asofdate,asofdateflow,trade_no,fo_system,isin,portfolio,counterparty,
                            target_instrument_type,issue,maturity_date,value_date,currency,amount,eur_amount_0d,
                            eur_amount_7d,eur_amount_30d,eur_amount_3m,lcr_inflow,lcr_outflow,reserve_amount,
                            exposure_class,hqla_level,reporting_line_lcr,record_type,adjustment_reference,created_by)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            output_id,context.asofdate,context.asofdateflow,row.get("tradeNo"),row.get("foSystem"),
                            row.get("isin"),row.get("portfolio"),row.get("counterparty"),row.get("targetInstrumentType"),
                            row.get("issue"),row.get("maturityDate"),row.get("valueDate"),row.get("currency"),
                            row.get("amount"),row.get("eurAmount0d"),row.get("eurAmount7d"),row.get("eurAmount30d"),
                            row.get("eurAmount3m"),row.get("lcrInflow"),row.get("lcrOutflow"),row.get("reserve"),
                            row.get("exposureClass"),row.get("hqlaLevel"),row.get("reportingLineLcr"),record_type,
                            batch_reference,user,
                        ),
                    )
                    connection.execute(
                        f"""INSERT INTO {self.schema}.output_adjustment_links(
                            output_record_id,source_output_record_id,parent_output_record_id,adjustment_reference,record_type,item_position)
                            VALUES(%s,%s,%s,%s,%s,%s)""",
                        (output_id,source_id,parent_id,batch_reference,record_type,position),
                    )
            return output_ids
