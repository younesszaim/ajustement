import copy

import pytest
import yaml

from app.config import ADDITIVE_MEASURES, EDITABLE_FIELDS, FIELD_DEPENDENCIES, STAGE_DEPENDENCIES
from app.data_dictionary import DEFAULT_DICTIONARY, DataDictionary, FIELDS
from lib.enrichments.registry import REGISTRY


def test_dictionary_drives_permissions_labels_and_dependencies():
    assert EDITABLE_FIELDS == FIELDS.api_names("editable")
    assert ADDITIVE_MEASURES == FIELDS.api_names("additive")
    assert FIELD_DEPENDENCIES["maturityDate"] == {"buckets"}
    assert FIELDS.label_for_api("reportingLineLcr") == "Reporting Line LCR"


def test_every_declared_producer_and_stage_is_registered():
    producers = {field.producer for field in FIELDS.fields.values() if field.producer}
    assert producers <= set(REGISTRY)
    assert set(STAGE_DEPENDENCIES) == set(REGISTRY)


def test_duplicate_api_name_fails_at_startup(tmp_path):
    raw = yaml.safe_load(DEFAULT_DICTIONARY.read_text())
    raw = copy.deepcopy(raw)
    raw["fields"]["currency"]["api"] = raw["fields"]["amount"]["api"]
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="Duplicate api"):
        DataDictionary(path)
