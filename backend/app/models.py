"""Validated HTTP contracts shared by the FastAPI endpoints.

Names use the frontend's camelCase JSON convention. ``LimonContext`` is present
on every business mutation so a row ID is never interpreted outside its exact
as-of date and version.
"""

from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


EXAMPLE_CONTEXT = {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09",
}


class LimonContext(BaseModel):
    asofdate: date
    asofdateflow: datetime


class AdjustmentRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "rowId": "SIM-ROW-0001",
                "changes": {"amount": 1250000, "exposureClass": "SOVEREIGN"},
            }
        }
    )

    context: LimonContext
    rowId: str
    changes: dict[str, Any]


class CommitRequest(AdjustmentRequest):
    """A preview promoted to a durable commit.

    ``expectedVersion`` detects changes since preview. ``idempotencyKey`` must
    be reused when retrying the same click, preventing duplicate output rows.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "rowId": "SIM-ROW-0001",
                "changes": {"amount": 1250000, "exposureClass": "SOVEREIGN"},
                "reason": "Correct classification after source review",
                "expectedVersion": "copy-rowVersion-from-preview",
                "idempotencyKey": "a9baa15f-2062-448d-845b-402842ace870",
            }
        }
    )

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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "items": [
                    {"rowId": "SIM-ROW-0001", "changes": {"amount": 1250000}},
                    {"rowId": "SIM-ROW-0002", "changes": {"maturityDate": "2026-09-30"}},
                ],
            }
        }
    )

    context: LimonContext
    items: list[BatchPreviewItem] = Field(min_length=1)


class BatchCommitRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "items": [
                    {
                        "rowId": "SIM-ROW-0001",
                        "changes": {"amount": 1250000},
                        "expectedVersion": "copy-first-rowVersion",
                    },
                    {
                        "rowId": "SIM-ROW-0002",
                        "changes": {"maturityDate": "2026-09-30"},
                        "expectedVersion": "copy-second-rowVersion",
                    },
                ],
                "reason": "Apply reviewed corrections for the reporting run",
                "idempotencyKey": "20c2edc2-7487-42f1-ac9c-cae01aa2af02",
            }
        }
    )

    context: LimonContext
    items: list[BatchAdjustmentItem] = Field(min_length=1)
    reason: str = Field(min_length=5)
    idempotencyKey: str = Field(min_length=8)


class RevertAdjustmentRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "rowId": "SIM-ROW-0001",
                "reason": "Revert after functional review",
                "idempotencyKey": "c36303ac-fc38-41a9-9ca2-7ee879920746",
            }
        }
    )

    context: LimonContext
    rowId: str
    reason: str = Field(min_length=5)
    idempotencyKey: str = Field(min_length=8)


class CancelTradeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"context": EXAMPLE_CONTEXT, "rowId": "SIM-ROW-0001"}
        }
    )

    context: LimonContext
    rowId: str


class CancelTradeCommitRequest(CancelTradeRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "rowId": "SIM-ROW-0001",
                "reason": "Trade cancelled by source system owner",
                "expectedVersion": "copy-rowVersion-from-cancellation-preview",
                "idempotencyKey": "f2ddf44c-4474-49e0-a1e9-b4b465125403",
            }
        }
    )

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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "context": EXAMPLE_CONTEXT,
                "draftId": "4ed537c0-5ad0-4b3f-b296-ced603c44b31",
                "fields": {
                    "foSystem": "Orchestrade",
                    "targetInstrumentType": "SECURITY",
                    "isin": "FR0000000001",
                    "issue": "Development proxy",
                    "valueDate": "2026-08-06",
                    "maturityDate": "2026-08-25",
                    "currency": "EUR",
                    "amount": 500000,
                    "portfolio": "LIQUIDITY",
                    "counterparty": "CP_PROXY",
                },
            }
        }
    )

    context: LimonContext
    draftId: str = Field(min_length=8)
    fields: ProxyFields


class ProxyCommitRequest(ProxyPreviewRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                **ProxyPreviewRequest.model_config["json_schema_extra"]["example"],
                "reason": "Temporary proxy for missing source trade",
                "idempotencyKey": "7f77c364-e274-40cb-8139-aa86efca19c4",
            }
        }
    )

    reason: str = Field(min_length=5)
    idempotencyKey: str = Field(min_length=8)
