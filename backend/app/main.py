import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .models import (
    AdjustmentRequest,
    CommitRequest,
    BatchCommitRequest,
    BatchPreviewRequest,
    RevertAdjustmentRequest,
    CancelTradeRequest,
    CancelTradeCommitRequest,
    ProxyPreviewRequest,
    ProxyCommitRequest,
    LimonContext,
)
from .storage import build_repository
from .services import (
    AdjustmentService,
    ConflictError,
    DomainError,
    InfrastructureError,
)

load_dotenv()
storage_mode = os.getenv("STORAGE_MODE", "supabase").lower()
app = FastAPI(title="LiMon Adjustment Manager API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
repo = build_repository()
service = AdjustmentService(repo)


def audit(event, metadata, context=None, row_id=None):
    repo.record_action(
        event, os.getenv("LOCAL_USER", "developer@example"), metadata, context, row_id
    )


def fail(exc):
    status = (
        503
        if isinstance(exc, InfrastructureError)
        else 409
        if isinstance(exc, ConflictError)
        else 422
    )
    raise HTTPException(status, str(exc))


@app.get("/api/health")
def health():
    result = {
        "status": "ok",
        "mode": storage_mode,
        "project": os.getenv("ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf"),
    }
    if hasattr(repo, "health"):
        result["storage"] = repo.health()
    if storage_mode == "hybrid_sim":
        result["simulatedFailurePoint"] = os.getenv(
            "SIMULATED_FAILURE_POINT"
        ) or None
    return result


@app.get("/api/asofdates")
def dates():
    return repo.asofdates()


@app.get("/api/versions")
def versions(asofdate: str):
    result = repo.versions(asofdate)
    audit("DATE_SELECTED", {"asofdate": asofdate, "availableVersions": len(result)})
    return result


@app.get("/api/trades")
def trades(
    asofdate: str,
    asofdateflow: str,
    search: str = "",
    foSystem: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
):
    try:
        context = LimonContext(asofdate=asofdate, asofdateflow=asofdateflow)
        items, total = repo.search(context, search, foSystem, page, pageSize)
        audit(
            "TRADE_SEARCHED",
            {"search": search, "foSystem": foSystem, "page": page, "resultRows": total},
            context,
        )
        return {"items": items, "total": total}
    except (DomainError, ValueError) as exc:
        fail(exc)


@app.get("/api/trades/{row_id}")
def detail(row_id: str, asofdate: str, asofdateflow: str):
    try:
        context = LimonContext(asofdate=asofdate, asofdateflow=asofdateflow)
        result = repo.get_effective_trade(context, row_id)
        audit("TRADE_VIEWED", {}, context, row_id)
        return result
    except (DomainError, ValueError) as exc:
        fail(exc)


@app.get("/api/trades/{row_id}/history")
def history(row_id: str):
    return repo.get_history(row_id)


@app.get("/api/trades/{row_id}/lineage")
def lineage(row_id: str, asofdate: str, asofdateflow: str):
    try:
        return repo.get_lineage(
            LimonContext(asofdate=asofdate, asofdateflow=asofdateflow), row_id
        )
    except (DomainError, ValueError) as exc:
        fail(exc)


@app.get("/api/adjustments/history")
def global_history(asofdate: str = "", asofdateflow: str = ""):
    return repo.get_global_history(asofdate, asofdateflow)


@app.post("/api/adjustments/impact")
def impact(req: AdjustmentRequest):
    return {"impactedStages": service.resolver.resolve(set(req.changes))}


@app.post("/api/adjustments/preview")
def preview(req: AdjustmentRequest):
    try:
        result = service.preview(req.context, req.rowId, req.changes)
        audit(
            "PREVIEW_COMPLETED",
            {
                "changedFields": list(req.changes),
                "impactedStages": result["impactedStages"],
            },
            req.context,
            req.rowId,
        )
        return result
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/cancel/preview")
def cancel_preview(req: CancelTradeRequest):
    try:
        return service.preview_cancellation(req.context, req.rowId)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/cancel/commit")
def cancel_commit(req: CancelTradeCommitRequest):
    try:
        return service.commit_cancellation(
            req, os.getenv("LOCAL_USER", "developer@example")
        )
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/proxy/preview")
def proxy_preview(req: ProxyPreviewRequest):
    try:
        return service.preview_proxy(req.context, req.draftId, req.fields)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/proxy/commit")
def proxy_commit(req: ProxyCommitRequest):
    try:
        return service.commit_proxy(
            req, os.getenv("LOCAL_USER", "developer@example")
        )
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/commit")
def commit(req: CommitRequest):
    try:
        return service.commit(req, os.getenv("LOCAL_USER", "developer@example"))
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/batch/commit")
def batch_commit(req: BatchCommitRequest):
    try:
        return service.commit_batch(req, os.getenv("LOCAL_USER", "developer@example"))
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/batch/preview")
def batch_preview(req: BatchPreviewRequest):
    try:
        result = service.preview_batch(req.context, req.items)
        audit(
            "PREVIEW_COMPLETED",
            {
                "batch": True,
                "tradeCount": result["tradeCount"],
                "impactedStages": result["impactedStages"],
            },
            req.context,
        )
        return result
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/{batch_id}/revert")
def revert_adjustment(batch_id: str, req: RevertAdjustmentRequest):
    try:
        return service.revert_adjustment(
            batch_id, req, os.getenv("LOCAL_USER", "developer@example")
        )
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/{batch_reference}/reconcile")
def reconcile_adjustment(batch_reference: str):
    try:
        if not hasattr(repo, "reconcile_adjustment"):
            raise InfrastructureError(
                "Reconciliation is available only in hybrid storage mode."
            )
        return repo.reconcile_adjustment(batch_reference)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)
