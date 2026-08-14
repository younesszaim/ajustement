"""Small contracts shared by calculation functions and the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import pandas as pd


class EnrichmentError(ValueError):
    """A calculation cannot produce a safe, deterministic result."""


@dataclass(frozen=True)
class CalculationContext:
    """Read-only execution information available to business functions."""

    stage: str
    mapping_name: str | None = None
    mapping_source: str | None = None


CalculationFunction = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class EnrichmentDefinition:
    """Registry entry describing one independently testable calculation."""

    stage: str
    function: CalculationFunction
    kind: Literal["rule", "parameter"]
    outputs: tuple[str, ...]
    required_inputs: tuple[str, ...] = ()
    mapping_name: str | None = None


def validate_frame(frame: pd.DataFrame, required: tuple[str, ...], stage: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise EnrichmentError(f'{stage}: missing input columns: {", ".join(missing)}')
    if frame.empty:
        raise EnrichmentError(f"{stage}: the input DataFrame is empty")


def execution_record(definition: EnrichmentDefinition, context: CalculationContext, rows: int) -> dict[str, Any]:
    return {
        "stage": definition.stage,
        "function": definition.function.__name__,
        "type": definition.kind,
        "mappingName": context.mapping_name,
        "mappingSource": context.mapping_source,
        "outputFields": list(definition.outputs),
        "processedRows": rows,
        "status": "SUCCEEDED",
    }
