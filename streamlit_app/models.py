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
class Preview:
    """The three rows displayed before an adjustment is committed."""
    original: dict
    reversal: dict
    adjusted: dict
    calculation_steps: list[str] = field(default_factory=list)
