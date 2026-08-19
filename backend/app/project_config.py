"""Project-specific choices exposed to adjustment users.

These values are intentionally independent from the Parquet parameter tables
used by the calculation pipeline. They define the small, reviewed set of values
that a user may select manually for controlled output fields.
"""

from .data_dictionary import FIELDS


A = FIELDS.api


CONTROLLED_FIELD_OPTIONS = {
    A("exposure_class"): {
        "displayName": FIELDS.field("exposure_class").label,
        "options": ("CORPORATE", "FINANCIAL", "SOVEREIGN"),
        "producerStage": "exposure_class",
        "downstreamStages": ("hqla", "reporting_lines", "lcr_impacts", "ldp_impacts"),
    },
    A("hqla_level"): {
        "displayName": FIELDS.field("hqla_level").label,
        "options": ("L1", "L2A", "L2B", "NON_HQLA"),
        "producerStage": "hqla",
        "downstreamStages": ("reporting_lines", "lcr_impacts", "ldp_impacts"),
    },
    A("reporting_line_lcr"): {
        "displayName": FIELDS.field("reporting_line_lcr").label,
        "options": ("RL_LOAN_01", "RL_SEC_01", "RL_SEC_03"),
        "producerStage": "reporting_lines",
        "downstreamStages": ("lcr_impacts", "ldp_impacts"),
    },
}


def controlled_fields_payload():
    """Return a JSON-safe description for the frontend dropdowns."""
    return [
        {
            "fieldName": field_name,
            "displayName": definition["displayName"],
            "options": list(definition["options"]),
            "producerStage": definition["producerStage"],
            "downstreamStages": list(definition["downstreamStages"]),
        }
        for field_name, definition in CONTROLLED_FIELD_OPTIONS.items()
    ]


def controlled_selections(changes):
    """Validate configured choices and return audit-friendly metadata."""
    selections = []
    for field_name, value in changes.items():
        definition = CONTROLLED_FIELD_OPTIONS.get(field_name)
        if not definition:
            continue
        if str(value) not in definition["options"]:
            allowed = ", ".join(definition["options"])
            raise ValueError(
                f'Value "{value}" is not allowed for {definition["displayName"]}. '
                f"Choose one of: {allowed}."
            )
        selections.append(
            {
                "field": field_name,
                "value": value,
                "selectionType": "PROJECT_CONFIG_OPTION",
                "displayName": definition["displayName"],
                "producerStage": definition["producerStage"],
                "downstreamStages": list(definition["downstreamStages"]),
            }
        )
    return selections
