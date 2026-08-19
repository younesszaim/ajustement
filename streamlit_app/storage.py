"""The only SQL boundary in the simple application."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Callable


def _identifier(value: str) -> str:
    """Quote a configured identifier; values never pass through this function."""
    return '"' + value.replace('"', '""') + '"'


class SqlOutputStore:
    """Output table access compatible with Vertica and PostgreSQL simulation."""
    def __init__(self, connection_factory: Callable, settings):
        """Configure one output table while delaying actual connections."""
        self.connection_factory = connection_factory
        self.settings = settings
        self.schema = settings.project["output_schema"]
        self.table = settings.project["output_table"]

    @property
    def qualified_table(self) -> str:
        """Return a safely quoted ``schema.table`` SQL identifier."""
        return f"{_identifier(self.schema)}.{_identifier(self.table)}"

    @contextmanager
    def _cursor(self):
        """Yield a cursor and always close its short-lived connection."""
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            yield cursor
        finally:
            connection.close()

    def context_values(self, key: str, filters: dict[str, object] | None = None) -> list:
        """Read distinct values for cascading context widgets.

        Example: requesting ``version`` with ``{"asofdate": "2026-08-06"}``
        returns only versions that exist for that date.
        """
        column = self.settings.column(key)
        clauses, params = [], []
        for filter_key, value in (filters or {}).items():
            clauses.append(f"{_identifier(self.settings.column(filter_key))} = %s")
            params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT DISTINCT {_identifier(column)} FROM {self.qualified_table}{where} ORDER BY 1 DESC"
        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]

    def search_active(self, context, text: str, limit: int = 1000) -> list[dict]:
        """Search only effective rows inside the complete snapshot context.

        A BASE or ADJUSTED row is excluded when a REVERSAL points to its output
        ID. The text predicate is executed by the database, not AG Grid.
        """
        f, t = self.settings.fields, self.settings.technical_fields
        types = self.settings.record_types
        aliases = [f[key]["column"] for key in self.settings.display_fields]
        columns = aliases + list(t.values())
        params = [context.asofdate, context.version, context.fo_system, context.leg_flag]
        text_clause = ""
        if text.strip():
            pattern = f"%{text.strip()}%"
            text_clause = (
                f" AND (CAST(o.{_identifier(f['trade_no']['column'])} AS VARCHAR) ILIKE %s"
                f" OR CAST(o.{_identifier(f['isin']['column'])} AS VARCHAR) ILIKE %s)"
            )
            params.extend([pattern, pattern])
        params.append(limit)
        query = f"""
            SELECT {', '.join('o.' + _identifier(column) for column in columns)}
            FROM {self.qualified_table} o
            WHERE o.{_identifier(f['asofdate']['column'])} = %s
              AND o.{_identifier(f['version']['column'])} = %s
              AND o.{_identifier(f['fo_system']['column'])} = %s
              AND o.{_identifier(f['leg_flag']['column'])} = %s
              AND o.{_identifier(t['record_type'])} IN (%s, %s)
              AND NOT EXISTS (
                SELECT 1 FROM {self.qualified_table} r
                WHERE r.{_identifier(t['record_type'])} = %s
                  AND r.{_identifier(t['parent_output_id'])} = o.{_identifier(f['output_id']['column'])}
              ){text_clause}
            ORDER BY o.{_identifier(f['trade_no']['column'])}
            LIMIT %s
        """
        params[4:4] = [types["base"], types["adjusted"], types["reversal"]]
        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_active(self, output_id: str) -> dict | None:
        """Return a complete row only if no reversal has canceled it."""
        f, t = self.settings.fields, self.settings.technical_fields
        types = self.settings.record_types
        query = f"""
            SELECT o.*
            FROM {self.qualified_table} o
            WHERE o.{_identifier(f['output_id']['column'])} = %s
              AND o.{_identifier(t['record_type'])} IN (%s, %s)
              AND NOT EXISTS (
                SELECT 1 FROM {self.qualified_table} r
                WHERE r.{_identifier(t['record_type'])} = %s
                  AND r.{_identifier(t['parent_output_id'])} = o.{_identifier(f['output_id']['column'])}
              )
        """
        with self._cursor() as cursor:
            cursor.execute(query, [output_id, types["base"], types["adjusted"], types["reversal"]])
            row = cursor.fetchone()
            columns = [getattr(description, "name", description[0]) for description in cursor.description]
            return dict(zip(columns, row)) if row else None

    def get_by_id(self, output_id: str) -> dict | None:
        """Read any historical row by ID, including an inactive original."""
        id_column = self.settings.column("output_id")
        query = f"SELECT * FROM {self.qualified_table} WHERE {_identifier(id_column)} = %s"
        with self._cursor() as cursor:
            cursor.execute(query, [output_id])
            row = cursor.fetchone()
            columns = [getattr(description, "name", description[0]) for description in cursor.description]
            return dict(zip(columns, row)) if row else None

    def reference_exists(self, reference: str) -> bool:
        """Detect an earlier output write during idempotent recovery."""
        column = self.settings.technical_fields["adjustment_reference"]
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT 1 FROM {self.qualified_table} WHERE {_identifier(column)} = %s LIMIT 1",
                [reference],
            )
            return cursor.fetchone() is not None

    def append(self, rows: list[dict]) -> None:
        """Insert complete output rows atomically within the output database.

        Every dictionary must contain the same keys because reversal and
        adjusted rows are full copies of the source business row.
        """
        if not rows:
            return
        # get_active() selects o.*, so every business column is preserved.
        columns = list(rows[0])
        if any(set(row) != set(columns) for row in rows):
            raise ValueError("Every appended output row must contain the same columns")
        query = (
            f"INSERT INTO {self.qualified_table} ({', '.join(_identifier(c) for c in columns)}) "
            f"VALUES ({', '.join(['%s'] * len(columns))})"
        )
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.executemany(query, [[row.get(column) for column in columns] for row in rows])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class PostgresOperationStore:
    """Persistence for the single PostgreSQL adjustment metadata table."""

    def __init__(self, connection_factory: Callable, schema: str = "adjustment_simple"):
        """Configure the table while keeping connection creation injectable."""
        self.connection_factory = connection_factory
        self.table = f"{_identifier(schema)}.{_identifier('adjustment_operations')}"

    def find_by_key(self, key: str) -> dict | None:
        """Find an existing intention by its unique retry key."""
        query = f"SELECT operation_id,status,payload,output_ids,error_message FROM {self.table} WHERE idempotency_key=%s"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, [key])
            row = cursor.fetchone()
            if not row:
                return None
            return dict(zip(("operation_id", "status", "payload", "output_ids", "error_message"), row))

    def get_operation(self, operation_id: str) -> dict | None:
        """Read the complete audit record needed by the revert workflow."""
        query = f"""
            SELECT operation_id,idempotency_key,operation_type,status,asofdate,version,
                   fo_system,leg_flag,source_output_id,reason,created_by,payload,output_ids,
                   error_message,created_at,committed_at,reverts_operation_id
            FROM {self.table} WHERE operation_id=%s
        """
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, [operation_id])
            row = cursor.fetchone()
            if not row:
                return None
            names = [description.name for description in cursor.description]
            return dict(zip(names, row))

    def create(self, operation: dict) -> None:
        """Insert a PENDING intention; duplicate retry keys are ignored."""
        query = f"""
            INSERT INTO {self.table}(
                operation_id,idempotency_key,operation_type,status,asofdate,version,
                fo_system,leg_flag,source_output_id,reason,created_by,payload,reverts_operation_id
            ) VALUES (%s,%s,%s,'PENDING',%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (idempotency_key) DO NOTHING
        """
        values = [
            operation[key] for key in (
                "operation_id", "idempotency_key", "operation_type", "asofdate", "version",
                "fo_system", "leg_flag", "source_output_id", "reason", "created_by"
            )
        ] + [json.dumps(operation["payload"], default=str), operation.get("reverts_operation_id")]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, values)

    def set_status(self, operation_id: str, status: str, output_ids=None, error_message=None) -> None:
        """Record progress or failure after an output-write attempt."""
        query = f"""
            UPDATE {self.table}
            SET status=%s, output_ids=%s::jsonb, error_message=%s,
                committed_at=CASE WHEN %s='COMMITTED' THEN now() ELSE committed_at END
            WHERE operation_id=%s
        """
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, [status, json.dumps(output_ids), error_message, status, operation_id])

    def commit_revert(self, revert_operation_id: str, target_operation_id: str, output_ids: list[str]) -> None:
        """Confirm the revert and mark its target reverted in one PG transaction."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {self.table}
                SET status='COMMITTED',output_ids=%s::jsonb,error_message=NULL,committed_at=now()
                WHERE operation_id=%s
                """,
                [json.dumps(output_ids), revert_operation_id],
            )
            cursor.execute(
                f"UPDATE {self.table} SET status='REVERTED' WHERE operation_id=%s AND status IN ('COMMITTED','REVERTED')",
                [target_operation_id],
            )

    def list_recent(self, limit: int = 100) -> list[dict]:
        """Return newest operations, including payload needed by Review."""
        query = f"""
            SELECT operation_id,operation_type,status,asofdate,version,fo_system,leg_flag,
                   source_output_id,reason,created_by,payload,output_ids,error_message,created_at,committed_at,
                   reverts_operation_id
            FROM {self.table} ORDER BY created_at DESC LIMIT %s
        """
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, [limit])
            names = [description.name for description in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
