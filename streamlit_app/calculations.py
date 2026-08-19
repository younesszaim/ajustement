"""Ordered, replaceable LiMon recalculation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import time
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Stage:
    """Describe one function and the semantic fields it normally produces."""

    name: str
    function: Callable[[pd.DataFrame, dict[str, str]], pd.DataFrame]
    outputs: frozenset[str]


class Calculation:
    """Demonstration calculation functions executed in business order.

    Every method receives and returns a DataFrame, so the same functions can
    later process one selected trade or a batch of selected trades.
    """

    def exposure_class(self, df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
        """Calculate exposure class; the demo preserves the existing value."""
        # The real project should replace this body with its mapping function.
        return df.copy()

    def reportline_code(self, df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
        """Derive a demonstration reporting line from exposure class."""
        result = df.copy()
        demonstration_mapping = {
            "CENTRAL_BANK": "RL_SEC_01",
            "SOVEREIGN": "RL_SEC_01",
            "FINANCIAL": "RL_SEC_03",
            "CORPORATE": "RL_LOAN_01",
            "RETAIL": "RL_LOAN_01",
        }
        exposure = columns["exposure_class"]
        reportline = columns["reporting_line_lcr"]
        result[reportline] = result[exposure].map(demonstration_mapping).fillna(result[reportline])
        return result

    def maturity_date(self, df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
        """Normalize maturity date before time-bucket calculation."""
        result = df.copy()
        maturity = columns["maturity_date"]
        result[maturity] = pd.to_datetime(result[maturity]).dt.date
        return result

    def calculate_buckets(self, df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
        """Allocate the selected Cash/Titre amount to one demo time bucket."""
        result = df.copy()
        for index, row in result.iterrows():
            leg = int(row[columns["leg_flag"]])
            amount_key = "cash_amount_eur" if leg == 0 else "security_amount_eur"
            amount = float(row[columns[amount_key]] or 0)
            maturity = date.fromisoformat(str(row[columns["maturity_date"]])[:10])
            asofdate = date.fromisoformat(str(row[columns["asofdate"]])[:10])
            days = (maturity - asofdate).days
            result.at[index, columns["eur_amount_7d"]] = amount if days <= 7 else 0.0
            result.at[index, columns["eur_amount_30d"]] = amount if 7 < days <= 30 else 0.0
            result.at[index, columns["eur_amount_3m"]] = amount if days > 30 else 0.0
        return result

    def calculate_ldp_impacts(self, df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
        """Calculate the small LDP-impact subset present in the prototype."""
        result = df.copy()
        for index, row in result.iterrows():
            leg = int(row[columns["leg_flag"]])
            cash = float(row[columns["cash_amount_eur"]] or 0)
            security = float(row[columns["security_amount_eur"]] or 0)
            result.at[index, columns["ldp_impact_asset"]] = security if leg == 1 else 0.0
            result.at[index, columns["ldp_impact_asset_cash"]] = cash if leg == 0 else 0.0
            result.at[index, columns["ldp_impact_lcr"]] = cash if leg == 0 else security
        return result


class CalculationPipeline:
    """Execute the minimum ordered suffix affected by manual changes."""

    def __init__(self, calculation: Calculation | None = None):
        """Declare calculation order explicitly instead of using reflection."""
        calculation = calculation or Calculation()
        self.stages = [
            Stage("exposure_class", calculation.exposure_class, frozenset({"exposure_class"})),
            Stage("reportline_code", calculation.reportline_code, frozenset({"reporting_line_lcr"})),
            Stage("maturity_date", calculation.maturity_date, frozenset({"maturity_date"})),
            Stage(
                "calculate_buckets",
                calculation.calculate_buckets,
                frozenset({"eur_amount_7d", "eur_amount_30d", "eur_amount_3m"}),
            ),
            Stage(
                "calculate_ldp_impacts",
                calculation.calculate_ldp_impacts,
                frozenset({"ldp_impact_asset", "ldp_impact_asset_cash", "ldp_impact_lcr"}),
            ),
        ]

        # Amount is an input to bucket calculation. Unlike a manually supplied
        # stage output, it must run calculate_buckets itself, not the next stage.
        self.input_start_stage = {
            "cash_amount_eur": "calculate_buckets",
            "security_amount_eur": "calculate_buckets",
            "asofdate": "calculate_buckets",
        }

    def run(
        self,
        row: dict,
        columns: dict[str, str],
        overrides: dict[str, object],
        progress_callback: Callable[[str, int, int, str], None] | None = None,
        delay_seconds: float = 0.0,
    ) -> tuple[dict, list[str]]:
        """Run affected stages and return the row plus executed stage names.

        Exposure change starts at reportline; reportline change starts at
        maturity; amount change starts at buckets. With several changes, the
        earliest required stage wins.
        """
        frame = pd.DataFrame([row])
        executed = []

        # Apply choices before the first stage so the first downstream function
        # sees the new values. The service already does this when constructing
        # its adjusted row, but keeping the pipeline autonomous makes it safe to
        # reuse from tests, batch jobs or another API endpoint.
        for field, value in overrides.items():
            frame.loc[:, columns[field]] = value

        selected_stages = self.stages[self._start_index(set(overrides)):]
        total = len(selected_stages)
        for index, stage in enumerate(selected_stages):
            # The callback updates an external job record. Calculation code does
            # not import FastAPI, Streamlit or any job-storage implementation.
            if progress_callback:
                progress_callback(stage.name, index, total, "RUNNING")
            if delay_seconds:
                # Development-only latency makes progress behavior testable.
                # Production leaves this at zero and pays no artificial delay.
                time.sleep(delay_seconds)
            before_count = len(frame)
            frame = stage.function(frame, columns)
            if len(frame) != before_count:
                raise ValueError(f"{stage.name} changed row count from {before_count} to {len(frame)}")

            # A downstream function may calculate a field the user also changed.
            # Reapply explicit choices after every stage so user responsibility
            # wins without skipping the rest of the dependency chain.
            for field, value in overrides.items():
                frame.loc[:, columns[field]] = value
            executed.append(stage.name)
            if progress_callback:
                progress_callback(stage.name, index + 1, total, "COMPLETED")

        result = dict(row)
        result.update({key: value for key, value in frame.iloc[0].to_dict().items() if not pd.isna(value)})
        return result, executed

    def _start_index(self, changed_fields: set[str]) -> int:
        """Find the earliest stage required by all changed fields."""
        indexes = []
        for field in changed_fields:
            if field in self.input_start_stage:
                indexes.append(self._index(self.input_start_stage[field]))
                continue
            for index, stage in enumerate(self.stages):
                if field in stage.outputs:
                    # The user already supplied this stage's output.
                    indexes.append(index + 1)
                    break
        return min(indexes, default=0)

    def _index(self, stage_name: str) -> int:
        """Resolve a reviewed stage name to its position."""
        return next(index for index, stage in enumerate(self.stages) if stage.name == stage_name)


_DEMO_PIPELINE = CalculationPipeline()


def recalculate_demo(
    row: dict,
    columns: dict[str, str],
    overrides: dict[str, object] | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    delay_seconds: float = 0.0,
) -> tuple[dict, list[str]]:
    """Configured adapter from a row dictionary to the DataFrame pipeline."""
    return _DEMO_PIPELINE.run(
        row,
        columns,
        overrides or {},
        progress_callback=progress_callback,
        delay_seconds=delay_seconds,
    )
