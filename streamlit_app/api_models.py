"""Explicit HTTP request contracts for the small API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContextBody(BaseModel):
    asofdate: str
    version: str
    fo_system: str
    leg_flag: int = Field(ge=0, le=1)


class AdjustmentBody(BaseModel):
    context: ContextBody
    source_output_id: str
    new_amount: float
    reason: str = Field(min_length=1)
    idempotency_key: str
    changes: dict[str, str | float | int | None] = Field(default_factory=dict)


class RevertBody(BaseModel):
    reason: str = Field(min_length=1)
    idempotency_key: str
