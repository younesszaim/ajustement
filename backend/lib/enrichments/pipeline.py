"""Orchestrate registered DataFrame calculations for preview and commit."""

from __future__ import annotations

import pandas as pd

from .contracts import CalculationContext, EnrichmentError, execution_record
from .registry import REGISTRY


class DataFrameCalculationAdapter:
    """Bridge the row-oriented API to vector-friendly LiMon functions."""

    def __init__(self, mapping_provider=None):
        if mapping_provider is None or not hasattr(mapping_provider, "parameter_table"):
            raise EnrichmentError("A manifest-backed parameter provider is required for LiMon calculations")
        self.mapping_provider = mapping_provider

    def recalculate(self, row: dict, stages: list[str]):
        frame = pd.DataFrame([row])
        recalculated: list[str] = []
        executions: list[dict] = []
        for stage in stages:
            definition = REGISTRY.get(stage)
            if definition is None:
                raise EnrichmentError(f'No enrichment function is registered for stage "{stage}"')
            source = None
            try:
                if definition.kind == "parameter":
                    parameter, source = self.mapping_provider.parameter_table(definition.mapping_name)
                    context = CalculationContext(stage=stage, mapping_name=definition.mapping_name, mapping_source=source)
                    before = len(frame)
                    frame = definition.function(frame, parameter, context)
                    if len(frame) != before:
                        raise EnrichmentError(f"{stage}: row count changed from {before} to {len(frame)}")
                else:
                    context = CalculationContext(stage=stage)
                    before = len(frame)
                    frame = definition.function(frame, context)
                    if len(frame) != before:
                        raise EnrichmentError(f"{stage}: row count changed from {before} to {len(frame)}")
            except EnrichmentError:
                raise
            recalculated.extend(definition.outputs)
            executions.append(execution_record(definition, context, len(frame)))
        # Start from the domain row so intentional ``None`` values (for example
        # a not-yet-persisted proxy id) are not mistaken for pandas missing data.
        clean_row = dict(row)
        clean_row.update({key: value for key, value in frame.iloc[0].to_dict().items() if not pd.isna(value)})
        return clean_row, list(dict.fromkeys(recalculated)), executions
