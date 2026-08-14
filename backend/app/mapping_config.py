"""Controlled adjustment fields and their downstream LiMon calculations.

The mapping rows do not belong in PostgreSQL.  This config describes how a
business field uses a mapping; the JSON manifest resolves the mapping name to
the latest immutable Parquet object.
"""

from .data_dictionary import FIELDS

A = FIELDS.api

MAPPING_FIELDS = {
    A("exposure_class"): {
        "mappingName": "exposure_class_mapping",
        "displayName": FIELDS.field("exposure_class").label,
        "description": "Possible outputs from the latest exposure-class mapping.",
        "outputColumn": FIELDS.parquet("exposure_class"),
        "producerStage": "exposure_class",
        "recalculationStartStage": "hqla",
        "downstreamStages": ["hqla", "reporting_lines", "lcr_impacts"],
    },
    A("hqla_level"): {
        "mappingName": "hqla_mapping",
        "displayName": FIELDS.field("hqla_level").label,
        "description": "Possible outputs from the latest HQLA mapping.",
        "outputColumn": FIELDS.parquet("hqla_level"),
        "producerStage": "hqla",
        "recalculationStartStage": "reporting_lines",
        "downstreamStages": ["reporting_lines", "lcr_impacts"],
    },
    A("reporting_line_lcr"): {
        "mappingName": "reporting_line_mapping",
        "displayName": FIELDS.field("reporting_line_lcr").label,
        "description": "Possible outputs from the latest reporting-line mapping.",
        "outputColumn": FIELDS.parquet("reporting_line_lcr"),
        "producerStage": "reporting_lines",
        "recalculationStartStage": "lcr_impacts",
        "downstreamStages": ["lcr_impacts"],
    },
}
