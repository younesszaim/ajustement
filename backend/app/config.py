from .mapping_config import MAPPING_FIELDS


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
}
FIELD_DEPENDENCIES.update(
    {
        field_name: {definition["recalculationStartStage"]}
        for field_name, definition in MAPPING_FIELDS.items()
    }
)
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

# Safe server-side filters exposed by the batch-selection API. The key is the
# stable domain field used by React; adapters translate it to physical columns.
BATCH_FILTER_FIELDS = {
    "tradeNo": {"type": "text"},
    "portfolio": {"type": "text"},
    "counterparty": {"type": "text"},
    "isin": {"type": "text"},
    "targetInstrumentType": {"type": "text"},
    "currency": {"type": "text"},
    "exposureClass": {"type": "text"},
    "hqlaLevel": {"type": "text"},
    "reportingLineLcr": {"type": "text"},
    "maturityDateFrom": {"type": "date"},
    "maturityDateTo": {"type": "date"},
    "amountMin": {"type": "number"},
    "amountMax": {"type": "number"},
}
