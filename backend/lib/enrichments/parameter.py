"""Generic and business-specific parameter-table enrichments."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.data_dictionary import FIELDS
from .contracts import CalculationContext, EnrichmentError, validate_frame


A = FIELDS.api
P = FIELDS.parquet


def apply_best_match_mapping(
    frame: pd.DataFrame,
    parameter: pd.DataFrame,
    *,
    inputs: dict[str, str],
    output: tuple[str, str],
    context: CalculationContext,
) -> pd.DataFrame:
    """Apply exact-or-wildcard mapping rows, preferring the most exact match.

    Two equally specific rows producing different values are rejected instead
    of silently choosing one. This is how duplicate/ambiguous mappings are made
    visible before an adjustment can be committed.
    """
    validate_frame(frame, tuple(inputs), context.stage)
    required_parameters = [*inputs.values(), output[1]]
    missing = [column for column in required_parameters if column not in parameter]
    if missing:
        raise EnrichmentError(f'{context.stage}: mapping misses columns: {", ".join(missing)}')
    result = frame.copy()
    for index, row in result.iterrows():
        candidates = parameter.copy()
        specificity = pd.Series(0, index=candidates.index, dtype="int64")
        for domain_column, parameter_column in inputs.items():
            values = candidates[parameter_column].astype(str)
            wanted = str(row[domain_column])
            candidates = candidates[(values == wanted) | (values == "*")]
            specificity = specificity.loc[candidates.index] + (candidates[parameter_column].astype(str) == wanted).astype(int)
        if candidates.empty:
            raise EnrichmentError(f"{context.stage}: no mapping row matches input row {index}")
        candidates = candidates.loc[specificity[specificity == specificity.max()].index]
        outputs = candidates[output[1]].dropna().unique().tolist()
        if len(outputs) != 1:
            raise EnrichmentError(f"{context.stage}: ambiguous mapping for input row {index}: {outputs}")
        result.at[index, output[0]] = outputs[0]
    return result


def enrich_reporting_line_lcr(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Calculate reportingLineLcr from the latest reporting-line parameter."""
    frame = frame.copy()
    if "maturityBucket" not in frame:
        validate_frame(frame, (A("maturity_date"), A("asofdate")), context.stage)
        frame[A("maturity_bucket")] = [
            "0-30D"
            if (datetime.fromisoformat(str(maturity)).date() - datetime.fromisoformat(str(asof)).date()).days <= 30
            else "31D+"
            for maturity, asof in zip(frame[A("maturity_date")], frame[A("asofdate")])
        ]
    return apply_best_match_mapping(
        frame,
        parameter,
        inputs={
            A("exposure_class"): P("exposure_class"),
            A("hqla_level"): P("hqla_level"),
            A("maturity_bucket"): P("maturity_bucket"),
        },
        output=(A("reporting_line_lcr"), P("reporting_line_lcr")),
        context=context,
    )


def enrich_instrument_classification(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    return apply_best_match_mapping(
        frame, parameter,
        inputs={A("target_instrument_type"): P("target_instrument_type")},
        output=(A("instrument_class"), "INSTRUMENT_CLASS"), context=context,
    )


def enrich_issuer(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Add issuer country and rating in two independently validated passes."""
    result = apply_best_match_mapping(
        frame, parameter, inputs={A("issue"): P("issue")},
        output=(A("issuer_country"), P("issuer_country")), context=context,
    )
    return apply_best_match_mapping(
        result, parameter, inputs={A("issue"): P("issue")},
        output=(A("issuer_rating"), P("issuer_rating")), context=context,
    )


def enrich_counterparty(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    return apply_best_match_mapping(
        frame, parameter, inputs={A("counterparty"): P("counterparty")},
        output=(A("counterparty_type"), P("counterparty_type")), context=context,
    )


def enrich_exposure_class(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    return apply_best_match_mapping(
        frame, parameter,
        inputs={
            A("instrument_class"): P("instrument_class"),
            A("counterparty_type"): P("counterparty_type"),
            A("issuer_country"): P("issuer_country"),
        },
        output=(A("exposure_class"), P("exposure_class")), context=context,
    )


def enrich_hqla(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    return apply_best_match_mapping(
        frame, parameter,
        inputs={
            A("exposure_class"): P("exposure_class"),
            A("instrument_class"): P("instrument_class"),
            A("issuer_rating"): P("issuer_rating"),
        },
        output=(A("hqla_level"), P("hqla_level")), context=context,
    )


def enrich_fx_rate(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Apply the as-of-independent example FX parameter to calculate EUR amount."""
    result = apply_best_match_mapping(
        frame, parameter, inputs={A("currency"): P("currency")},
        output=(A("fx_rate_to_eur"), P("fx_rate_to_eur")), context=context,
    )
    result[A("eur_amount_0d")] = result[A("amount")].astype(float) * result[A("fx_rate_to_eur")].astype(float)
    return result


def enrich_lcr_impacts(frame: pd.DataFrame, parameter: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Calculate LCR measures using factors selected by reporting line."""
    result = apply_best_match_mapping(
        frame, parameter, inputs={A("reporting_line_lcr"): P("reporting_line_lcr")},
        output=(A("lcr_outflow_factor"), P("lcr_outflow_factor")), context=context,
    )
    result = apply_best_match_mapping(
        result, parameter, inputs={A("reporting_line_lcr"): P("reporting_line_lcr")},
        output=(A("lcr_inflow_factor"), P("lcr_inflow_factor")), context=context,
    )
    result[A("lcr_outflow")] = result[A("eur_amount_0d")].astype(float) * result[A("lcr_outflow_factor")].astype(float)
    result[A("lcr_inflow")] = result[A("eur_amount_0d")].astype(float) * result[A("lcr_inflow_factor")].astype(float)
    return result
