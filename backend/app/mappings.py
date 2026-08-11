"""Mapping catalog boundary for adjustment value assistance and validation."""

from __future__ import annotations

from contextlib import contextmanager
import os

import psycopg
from psycopg.rows import dict_row

from .services import DomainError


class PostgresMappingProvider:
    def __init__(self, connection_factory, schema="mapping_sim"):
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

    def fields(self):
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT field_name,mapping_name,display_name,description,
                           source_path,output_column,producer_stage,downstream_stages
                    FROM {self.schema}.mapping_registry
                    WHERE is_active ORDER BY display_name"""
            ).fetchall()
        return [self._field(row) for row in rows]

    def field(self, field_name):
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT field_name,mapping_name,display_name,description,
                           source_path,output_column,producer_stage,downstream_stages
                    FROM {self.schema}.mapping_registry
                    WHERE field_name=%s AND is_active""",
                (field_name,),
            ).fetchone()
        return self._field(row) if row else None

    def values(self, field_name, search="", limit=50):
        definition = self.field(field_name)
        if not definition:
            raise DomainError(f'No active mapping is configured for field "{field_name}".')
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT DISTINCT row_payload ->> %s AS value
                    FROM {self.schema}.mapping_rows
                    WHERE mapping_name=%s
                      AND row_payload ->> %s IS NOT NULL
                      AND (%s='' OR row_payload ->> %s ILIKE '%%' || %s || '%%')
                    ORDER BY value LIMIT %s""",
                (
                    definition["outputColumn"],
                    definition["mappingName"],
                    definition["outputColumn"],
                    search,
                    definition["outputColumn"],
                    search,
                    limit,
                ),
            ).fetchall()
        return {"field": definition, "values": [row["value"] for row in rows]}

    def rows(self, mapping_name, search="", page=1, page_size=20):
        offset = (page - 1) * page_size
        with self.connection() as connection:
            definition = connection.execute(
                f"""SELECT field_name,mapping_name,display_name,description,
                           source_path,output_column,producer_stage,downstream_stages
                    FROM {self.schema}.mapping_registry
                    WHERE mapping_name=%s AND is_active""",
                (mapping_name,),
            ).fetchone()
            if not definition:
                raise DomainError(f'Mapping "{mapping_name}" is not configured.')
            where = "mapping_name=%s AND (%s='' OR row_payload::text ILIKE '%%' || %s || '%%')"
            total = connection.execute(
                f"SELECT count(*) AS count FROM {self.schema}.mapping_rows WHERE {where}",
                (mapping_name, search, search),
            ).fetchone()["count"]
            result = connection.execute(
                f"""SELECT row_number,row_payload FROM {self.schema}.mapping_rows
                    WHERE {where} ORDER BY row_number LIMIT %s OFFSET %s""",
                (mapping_name, search, search, page_size, offset),
            ).fetchall()
        return {
            "mapping": self._field(definition),
            "items": [
                {"rowNumber": row["row_number"], **row["row_payload"]}
                for row in result
            ],
            "page": page,
            "pageSize": page_size,
            "total": total,
        }

    def validate_overrides(self, changes):
        overrides = []
        for field_name, value in changes.items():
            definition = self.field(field_name)
            if not definition:
                continue
            available = self.values(field_name, str(value), 100)["values"]
            if str(value) not in available:
                raise DomainError(
                    f'Value "{value}" is not available in the latest mapping for {definition["displayName"]}.'
                )
            overrides.append(
                {
                    "field": field_name,
                    "value": value,
                    "selectionType": "MANUAL_MAPPING_OVERRIDE",
                    **definition,
                }
            )
        return overrides

    @staticmethod
    def _field(row):
        return {
            "fieldName": row["field_name"],
            "mappingName": row["mapping_name"],
            "displayName": row["display_name"],
            "description": row["description"],
            "sourcePath": row["source_path"],
            "outputColumn": row["output_column"],
            "producerStage": row["producer_stage"],
            "downstreamStages": list(row["downstream_stages"]),
        }


def build_mapping_provider():
    def connection():
        url = (
            os.getenv("MAPPING_DB_URL")
            or os.getenv("METADATA_DB_URL")
            or os.getenv("SUPABASE_DB_URL")
        )
        if not url:
            raise RuntimeError(
                "MAPPING_DB_URL, METADATA_DB_URL, or SUPABASE_DB_URL is required."
            )
        return psycopg.connect(url, connect_timeout=10, row_factory=dict_row)

    return PostgresMappingProvider(connection)
