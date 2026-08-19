"""Pure rule-based enrichments: DataFrame in, enriched DataFrame out."""

from __future__ import annotations

from datetime import datetime
import pandas as pd

from app.data_dictionary import FIELDS
from .contracts import CalculationContext, EnrichmentError, validate_frame

A = FIELDS.api


def select_leg_amount(frame: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Use the selected Cash/Titre EUR leg as the bucket calculation amount."""
    validate_frame(
        frame,
        (A("security_leg_flag"), A("cash_amount_eur"), A("security_amount_eur")),
        context.stage,
    )
    result = frame.copy()
    flags = pd.to_numeric(result[A("security_leg_flag")], errors="raise").astype(int)
    if not flags.isin((0, 1)).all():
        raise EnrichmentError("Security leg flag must be 0 (Cash) or 1 (Titre).")
    result[A("eur_amount_0d")] = [
        float(row[A("cash_amount_eur")]) if int(row[A("security_leg_flag")]) == 0
        else float(row[A("security_amount_eur")])
        for _, row in result.iterrows()
    ]
    return result


def calculate_buckets(frame: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Populate mutually exclusive amount buckets and a mapping input bucket."""
    validate_frame(frame, (A("eur_amount_0d"), A("maturity_date"), A("asofdate")), context.stage)
    result = frame.copy()
    for column in (A("eur_amount_7d"), A("eur_amount_30d"), A("eur_amount_3m")):
        result[column] = 0.0
    for index, row in result.iterrows():
        days = (datetime.fromisoformat(str(row[A("maturity_date")])).date() - datetime.fromisoformat(str(row[A("asofdate")])).date()).days
        amount = float(row[A("eur_amount_0d")])
        amount_column = A("eur_amount_7d") if days <= 7 else A("eur_amount_30d") if days <= 30 else A("eur_amount_3m")
        result.at[index, amount_column] = amount
        result.at[index, A("maturity_bucket")] = "0-30D" if days <= 30 else "31D+"
    return result


def calculate_ldp_impacts(frame: pd.DataFrame, context: CalculationContext) -> pd.DataFrame:
    """Derive the simulation LDP impact family from the selected leg and LCR impacts."""
    validate_frame(
        frame,
        (
            A("security_leg_flag"), A("cash_amount_eur"), A("security_amount_eur"),
            A("lcr_inflow"), A("lcr_outflow"),
        ),
        context.stage,
    )
    result = frame.copy()
    flags = pd.to_numeric(result[A("security_leg_flag")], errors="raise").astype(int)
    if not flags.isin((0, 1)).all():
        raise EnrichmentError("Security leg flag must be 0 (Cash) or 1 (Titre).")
    result[A("ldp_impact_asset")] = [
        float(row[A("security_amount_eur")]) if int(row[A("security_leg_flag")]) == 1 else 0.0
        for _, row in result.iterrows()
    ]
    result[A("ldp_impact_asset_cash_gestion")] = [
        float(row[A("cash_amount_eur")]) if int(row[A("security_leg_flag")]) == 0 else 0.0
        for _, row in result.iterrows()
    ]
    result[A("ldp_impact_inflow")] = result[A("lcr_inflow")].astype(float)
    result[A("ldp_impact_outflow")] = result[A("lcr_outflow")].astype(float)
    result[A("ldp_impact_lcr_reglementaire")] = (
        result[A("ldp_impact_asset")]
        + result[A("ldp_impact_inflow")]
        - result[A("ldp_impact_outflow")]
    )
    result[A("ldp_impact_lcr_gestion")] = (
        result[A("ldp_impact_asset_cash_gestion")]
        + result[A("ldp_impact_lcr_reglementaire")]
    )
    return result
