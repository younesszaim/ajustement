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
        pa.Table.from_pylist(
            [
                {"INPUT": "BANK", "OUTPUT": "FINANCIAL"},
                {"INPUT": "STATE", "OUTPUT": "SOVEREIGN"},
                {"INPUT": "OTHER", "OUTPUT": "FINANCIAL"},
            ]
        ),
        mapping_dir / "mapping-v1.parquet",
    )
    manifest = tmp_path / "latest.json"
    manifest.write_text(
        json.dumps({"test_mapping": "versions/mapping-v1.parquet"}),
        encoding="utf-8",
    )
    config = {
        "testField": {
            "mappingName": "test_mapping",
            "displayName": "Test field",
            "description": "Test mapping",
            "outputColumn": "OUTPUT",
            "producerStage": "test_stage",
            "recalculationStartStage": "next_stage",
            "downstreamStages": ["next_stage"],
        }
    }
    return ParquetMappingProvider(manifest, config)


def test_manifest_resolves_relative_parquet_and_distinct_values(tmp_path):
    mappings = provider(tmp_path)

    result = mappings.values("testField")

    assert result["field"]["sourcePath"] == "versions/mapping-v1.parquet"
    assert result["values"] == ["FINANCIAL", "SOVEREIGN"]
    assert mappings.values("testField", "sov")["values"] == ["SOVEREIGN"]


def test_mapping_rows_support_search_and_pagination(tmp_path):
    mappings = provider(tmp_path)

    first_page = mappings.rows("test_mapping", page=1, page_size=2)
    searched = mappings.rows("test_mapping", search="state")

    assert first_page["total"] == 3
    assert len(first_page["items"]) == 2
    assert first_page["items"][0]["rowNumber"] == 1
    assert searched["total"] == 1
    assert searched["items"][0]["OUTPUT"] == "SOVEREIGN"


def test_override_validation_returns_auditable_mapping_reference(tmp_path):
    mappings = provider(tmp_path)

    [override] = mappings.validate_overrides({"testField": "FINANCIAL"})

    assert override["mappingName"] == "test_mapping"
    assert override["sourcePath"] == "versions/mapping-v1.parquet"
    assert override["downstreamStages"] == ["next_stage"]

    with pytest.raises(DomainError, match="not available"):
        mappings.validate_overrides({"testField": "UNKNOWN"})
