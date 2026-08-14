from .mapping_config import MAPPING_FIELDS
from .data_dictionary import FIELDS


EDITABLE_FIELDS = FIELDS.api_names("editable")
ADDITIVE_MEASURES = FIELDS.api_names("additive")
FIELD_DEPENDENCIES = {
    field.api: set(field.starts)
    for field in FIELDS.fields.values()
    if field.starts
}
STAGE_DEPENDENCIES = {
    "instrument_classification": set(),
    "issuer_enrichment": set(),
    "counterparty_enrichment": set(),
    "eur_amount": set(),
    "buckets": {"eur_amount"},
    "exposure_class": {
        "instrument_classification",
        "issuer_enrichment",
        "counterparty_enrichment",
    },
    "hqla": {"instrument_classification", "issuer_enrichment", "exposure_class"},
    # Reporting-line mapping also consumes the maturity bucket produced by the
    # rule stage, so its dependency is explicit and testable.
    "reporting_lines": {"exposure_class", "hqla", "buckets"},
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
