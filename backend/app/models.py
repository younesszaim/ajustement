from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class LimonContext(BaseModel):
    asofdate: date
    asofdateflow: datetime


class AdjustmentRequest(BaseModel):
    context: LimonContext
    rowId: str
    changes: dict[str, Any]


class CommitRequest(AdjustmentRequest):
    reason: str = Field(min_length=5)
    expectedVersion: str
    idempotencyKey: str = Field(min_length=8)


class AdjustmentResult(BaseModel):
    adjustmentBatchId: str
    status: Literal["COMMITTED"] = "COMMITTED"
    insertedRecords: int = 2


class BatchAdjustmentItem(BaseModel):
    rowId: str
    changes: dict[str, Any]
    expectedVersion: str


class BatchPreviewItem(BaseModel):
    rowId: str
    changes: dict[str, Any]


class BatchPreviewRequest(BaseModel):
    context: LimonContext
    items: list[BatchPreviewItem] = Field(min_length=1)


class BatchCommitRequest(BaseModel):
    context: LimonContext
    items: list[BatchAdjustmentItem] = Field(min_length=1)
    reason: str = Field(min_length=5)
    idempotencyKey: str = Field(min_length=8)


class RevertAdjustmentRequest(BaseModel):
    context: LimonContext
    rowId: str
    reason: str = Field(min_length=5)
    idempotencyKey: str = Field(min_length=8)


class CancelTradeRequest(BaseModel):
    context: LimonContext
    rowId: str


class CancelTradeCommitRequest(CancelTradeRequest):
    reason: str = Field(min_length=5)
    expectedVersion: str
    idempotencyKey: str = Field(min_length=8)


class ProxyFields(BaseModel):
    foSystem: str = Field(min_length=1)
    targetInstrumentType: str = Field(min_length=1)
    isin: str = ""
    issue: str = ""
    valueDate: date
    maturityDate: date
    currency: str = Field(min_length=3, max_length=3)
    amount: float
    portfolio: str = Field(min_length=1)
    counterparty: str = Field(min_length=1)


class ProxyPreviewRequest(BaseModel):
    context: LimonContext
    draftId: str = Field(min_length=8)
    fields: ProxyFields


class ProxyCommitRequest(ProxyPreviewRequest):
    reason: str = Field(min_length=5)
    idempotencyKey: str = Field(min_length=8)
