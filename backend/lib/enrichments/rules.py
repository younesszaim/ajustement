"""Pure rule-based enrichments: DataFrame in, enriched DataFrame out."""

from __future__ import annotations

from datetime import datetime
import pandas as pd

from app.data_dictionary import FIELDS
from .contracts import CalculationContext, validate_frame

A = FIELDS.api


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
