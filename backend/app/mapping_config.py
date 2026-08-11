"""Controlled adjustment fields and their downstream LiMon calculations.

The mapping rows do not belong in PostgreSQL.  This config describes how a
business field uses a mapping; the JSON manifest resolves the mapping name to
the latest immutable Parquet object.
"""

MAPPING_FIELDS = {
    "exposureClass": {
        "mappingName": "exposure_class_mapping",
        "displayName": "Exposure class",
        "description": "Possible outputs from the latest exposure-class mapping.",
        "outputColumn": "EXPOSURE_CLASS",
        "producerStage": "exposure_class",
        "recalculationStartStage": "hqla",
        "downstreamStages": ["hqla", "reporting_lines", "lcr_impacts"],
    },
    "hqlaLevel": {
        "mappingName": "hqla_mapping",
        "displayName": "HQLA level",
        "description": "Possible outputs from the latest HQLA mapping.",
        "outputColumn": "HQLA_LEVEL",
        "producerStage": "hqla",
        "recalculationStartStage": "reporting_lines",
        "downstreamStages": ["reporting_lines", "lcr_impacts"],
    },
    "reportingLineLcr": {
        "mappingName": "reporting_line_mapping",
        "displayName": "Reporting line LCR",
        "description": "Possible outputs from the latest reporting-line mapping.",
        "outputColumn": "REPORTING_LINE_LCR",
        "producerStage": "reporting_lines",
        "recalculationStartStage": "lcr_impacts",
        "downstreamStages": ["lcr_impacts"],
    },
}
