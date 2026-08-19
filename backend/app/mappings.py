"""Manifest-driven Parquet mapping catalog."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pyarrow.parquet as parquet

from .services import DomainError


DEFAULT_MANIFEST = Path(__file__).parents[1] / "mapping_data" / "latest_mappings.json"


class ParquetMappingProvider:
    """Read mapping definitions from config and rows from manifest-selected Parquet."""

    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path).expanduser().resolve()
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

def build_mapping_provider():
    configured = os.getenv("MAPPING_MANIFEST_PATH")
    manifest = Path(configured).expanduser() if configured else DEFAULT_MANIFEST
    if not manifest.is_absolute():
        # Environment examples use a backend-relative path. Do not make it
        # depend on whether Uvicorn was launched from backend/ or project root.
        manifest = Path(__file__).parents[1] / manifest
    return ParquetMappingProvider(manifest)
