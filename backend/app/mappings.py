"""Manifest-driven Parquet mapping catalog."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pyarrow.parquet as parquet

from .mapping_config import MAPPING_FIELDS
from .services import DomainError


DEFAULT_MANIFEST = Path(__file__).parents[1] / "mapping_data" / "latest_mappings.json"


class ParquetMappingProvider:
    """Read mapping definitions from config and rows from manifest-selected Parquet."""

    def __init__(self, manifest_path: str | Path, field_config=None):
        self.manifest_path = Path(manifest_path).expanduser().resolve()
        self.field_config = field_config or MAPPING_FIELDS
        self._table_cache = {}

    def _manifest(self):
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DomainError(
                f'Cannot read mapping manifest "{self.manifest_path}": {exc}'
            ) from exc
        if not isinstance(manifest, dict):
            raise DomainError("The mapping manifest must be a JSON object.")
        return manifest

    def _source(self, mapping_name):
        source = self._manifest().get(mapping_name)
        if not isinstance(source, str) or not source.strip():
            raise DomainError(
                f'Mapping "{mapping_name}" has no Parquet path in the manifest.'
            )
        return source.strip()

    def _resolved_source(self, source):
        if "://" in source:
            return source
        return str((self.manifest_path.parent / source).resolve())

    def _table(self, source):
        resolved = self._resolved_source(source)
        if resolved not in self._table_cache:
            try:
                self._table_cache[resolved] = parquet.read_table(resolved)
            except Exception as exc:
                raise DomainError(
                    f'Cannot read Parquet mapping "{source}": {exc}'
                ) from exc
        return self._table_cache[resolved]

    def parameter_table(self, mapping_name):
        """Return a mapping as a DataFrame for the calculation pipeline.

        Enrichment functions deliberately receive their parameter table as an
        argument: they never know whether it came from local disk, S3 or a test
        fixture.  Only this provider resolves the manifest and reads Parquet.
        """
        source = self._source(mapping_name)
        return self._table(source).to_pandas(), source

    def fields(self):
        return sorted(
            (self.field(field_name) for field_name in self.field_config),
            key=lambda item: item["displayName"],
        )

    def field(self, field_name):
        config = self.field_config.get(field_name)
        if not config:
            return None
        source = self._source(config["mappingName"])
        return {
            "fieldName": field_name,
            "sourcePath": source,
            **{
                key: value
                for key, value in config.items()
                if key != "recalculationStartStage"
            },
        }

    def values(self, field_name, search="", limit=50):
        definition = self.field(field_name)
        if not definition:
            raise DomainError(f'No mapping is configured for field "{field_name}".')
        table = self._table(definition["sourcePath"])
        column = definition["outputColumn"]
        if column not in table.column_names:
            raise DomainError(
                f'Column "{column}" is missing from {definition["sourcePath"]}.'
            )
        query = search.casefold()
        available = {
            str(value)
            for value in table[column].to_pylist()
            if value is not None and (not query or query in str(value).casefold())
        }
        return {"field": definition, "values": sorted(available)[:limit]}

    def rows(self, mapping_name, search="", page=1, page_size=20):
        definition = next(
            (item for item in self.fields() if item["mappingName"] == mapping_name),
            None,
        )
        if not definition:
            raise DomainError(f'Mapping "{mapping_name}" is not configured.')
        records = self._table(definition["sourcePath"]).to_pylist()
        query = search.casefold()
        if query:
            records = [
                row
                for row in records
                if any(query in str(value).casefold() for value in row.values())
            ]
        offset = (page - 1) * page_size
        items = [
            {"rowNumber": index, **row}
            for index, row in enumerate(records[offset : offset + page_size], offset + 1)
        ]
        return {
            "mapping": definition,
            "items": items,
            "page": page,
            "pageSize": page_size,
            "total": len(records),
        }

    def validate_overrides(self, changes):
        overrides = []
        for field_name, value in changes.items():
            definition = self.field(field_name)
            if not definition:
                continue
            available = self.values(field_name, str(value), 200)["values"]
            if str(value) not in available:
                raise DomainError(
                    f'Value "{value}" is not available in {definition["displayName"]} mapping.'
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


def build_mapping_provider():
    configured = os.getenv("MAPPING_MANIFEST_PATH")
    manifest = Path(configured).expanduser() if configured else DEFAULT_MANIFEST
    if not manifest.is_absolute():
        # Environment examples use a backend-relative path. Do not make it
        # depend on whether Uvicorn was launched from backend/ or project root.
        manifest = Path(__file__).parents[1] / manifest
    return ParquetMappingProvider(manifest)
