import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.mappings import ParquetMappingProvider
from app.services import DomainError


def provider(tmp_path):
    mapping_dir = tmp_path / "versions"
    mapping_dir.mkdir()
    pq.write_table(
        pa.Table.from_pylist([{"INPUT": "BANK", "OUTPUT": "FINANCIAL"}]),
        mapping_dir / "mapping-v1.parquet",
    )
    manifest = tmp_path / "latest.json"
    manifest.write_text(
        json.dumps({"test_mapping": "versions/mapping-v1.parquet"}),
        encoding="utf-8",
    )
    return ParquetMappingProvider(manifest)


def test_manifest_resolves_relative_parquet_for_calculation(tmp_path):
    mappings = provider(tmp_path)
    frame, source = mappings.parameter_table("test_mapping")
    assert source == "versions/mapping-v1.parquet"
    assert frame.to_dict("records") == [{"INPUT": "BANK", "OUTPUT": "FINANCIAL"}]


def test_missing_manifest_entry_is_actionable(tmp_path):
    mappings = provider(tmp_path)
    with pytest.raises(DomainError, match="has no Parquet path"):
        mappings.parameter_table("unknown_mapping")
