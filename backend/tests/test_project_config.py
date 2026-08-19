import pytest

from app.project_config import controlled_fields_payload, controlled_selections


def test_controlled_field_payload_exposes_dropdown_options():
    fields = {item["fieldName"]: item for item in controlled_fields_payload()}
    assert fields["exposureClass"]["options"] == [
        "CORPORATE", "FINANCIAL", "SOVEREIGN"
    ]
    assert "L2B" in fields["hqlaLevel"]["options"]


def test_controlled_selection_is_validated_and_auditable():
    [selection] = controlled_selections({"hqlaLevel": "L2A"})
    assert selection["selectionType"] == "PROJECT_CONFIG_OPTION"
    assert selection["producerStage"] == "hqla"

    with pytest.raises(ValueError, match="not allowed"):
        controlled_selections({"hqlaLevel": "INVALID"})
