"""Explicit allowlist of calculation stages; no arbitrary dynamic imports."""

from .contracts import EnrichmentDefinition
from .parameter import (
    enrich_counterparty, enrich_exposure_class, enrich_fx_rate, enrich_hqla,
    enrich_instrument_classification, enrich_issuer, enrich_lcr_impacts,
    enrich_reporting_line_lcr,
)
from .rules import calculate_buckets
from app.data_dictionary import FIELDS

A = FIELDS.api


REGISTRY = {
    "instrument_classification": EnrichmentDefinition("instrument_classification", enrich_instrument_classification, "parameter", (A("instrument_class"),), (A("target_instrument_type"),), "instrument_classification_mapping"),
    "issuer_enrichment": EnrichmentDefinition("issuer_enrichment", enrich_issuer, "parameter", (A("issuer_country"), A("issuer_rating")), (A("issue"),), "issuer_mapping"),
    "counterparty_enrichment": EnrichmentDefinition("counterparty_enrichment", enrich_counterparty, "parameter", (A("counterparty_type"),), (A("counterparty"),), "counterparty_mapping"),
    "eur_amount": EnrichmentDefinition("eur_amount", enrich_fx_rate, "parameter", (A("fx_rate_to_eur"), A("eur_amount_0d")), (A("amount"), A("currency")), "fx_rate_mapping"),
    "buckets": EnrichmentDefinition("buckets", calculate_buckets, "rule", (A("eur_amount_7d"), A("eur_amount_30d"), A("eur_amount_3m"), A("maturity_bucket")), (A("eur_amount_0d"), A("maturity_date"), A("asofdate"))),
    "exposure_class": EnrichmentDefinition("exposure_class", enrich_exposure_class, "parameter", (A("exposure_class"),), (A("instrument_class"), A("counterparty_type"), A("issuer_country")), "exposure_class_mapping"),
    "hqla": EnrichmentDefinition("hqla", enrich_hqla, "parameter", (A("hqla_level"),), (A("exposure_class"), A("instrument_class"), A("issuer_rating")), "hqla_mapping"),
    "reporting_lines": EnrichmentDefinition("reporting_lines", enrich_reporting_line_lcr, "parameter", (A("reporting_line_lcr"),), (A("exposure_class"), A("hqla_level"), A("maturity_bucket")), "reporting_line_mapping"),
    "lcr_impacts": EnrichmentDefinition("lcr_impacts", enrich_lcr_impacts, "parameter", (A("lcr_outflow_factor"), A("lcr_inflow_factor"), A("lcr_outflow"), A("lcr_inflow")), (A("reporting_line_lcr"), A("eur_amount_0d")), "lcr_factor_mapping"),
}
