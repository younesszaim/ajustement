EDITABLE_FIELDS = {
    "targetInstrumentType",
    "issue",
    "maturityDate",
    "valueDate",
    "amount",
    "currency",
    "counterparty",
    "securityId",
    "exposureClass",
    "hqlaLevel",
    "reportingLineLcr",
}
ADDITIVE_MEASURES = {
    "amount",
    "eurAmount0d",
    "eurAmount7d",
    "eurAmount30d",
    "eurAmount3m",
    "lcrInflow",
    "lcrOutflow",
    "reserve",
}
FIELD_DEPENDENCIES = {
    "amount": {"eur_amount", "buckets"},
    "currency": {"eur_amount"},
    "maturityDate": {"buckets"},
    "valueDate": {"buckets"},
    "issue": {"issuer_enrichment"},
    "targetInstrumentType": {"instrument_classification"},
    "counterparty": {"counterparty_enrichment"},
    "securityId": {"instrument_classification"},
    # Manual overrides start after the stage that normally produces the field.
    "exposureClass": {"hqla"},
    "hqlaLevel": {"reporting_lines"},
    "reportingLineLcr": {"lcr_impacts"},
}
STAGE_DEPENDENCIES = {
    "instrument_classification": set(),
    "issuer_enrichment": set(),
    "counterparty_enrichment": set(),
    "eur_amount": set(),
    "buckets": set(),
    "exposure_class": {
        "instrument_classification",
        "issuer_enrichment",
        "counterparty_enrichment",
    },
    "hqla": {"instrument_classification", "issuer_enrichment", "exposure_class"},
    "reporting_lines": {"exposure_class", "hqla"},
    "lcr_impacts": {"reporting_lines", "buckets", "eur_amount"},
}
