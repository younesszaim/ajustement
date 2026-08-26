"""Small domain objects shared by the UI, service and tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Context:
    """Coordinates that identify exactly one immutable output snapshot."""
    asofdate: str
    version: str
    fo_system: str
    leg_flag: int


@dataclass(frozen=True)
class AdjustmentDraft:
    """One user intention shared by preview, commit and idempotent retry."""
    source_output_id: str
    new_amount: float
    reason: str
    idempotency_key: str
    changes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CancellationDraft:
    """One request to neutralize an active row with a single reversal."""
    source_output_id: str
    reason: str
    idempotency_key: str


@dataclass(frozen=True)
class Preview:
    """The three rows displayed before an adjustment is committed."""
    original: dict
    reversal: dict
    adjusted: dict
    calculation_steps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CancellationPreview:
    """Read-only view of the active row and its future cancellation row."""
    original: dict
    reversal: dict
