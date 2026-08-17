"""FastAPI composition root and HTTP boundary.

Endpoints in this module stay intentionally thin: validate the
Pydantic request, call a domain service/repository, audit relevant reads, and
translate known failures to HTTP status codes. Business row construction must
remain in ``services.py`` so preview, single commit and batch commit share it.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import psycopg

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")
from .models import (
    AdjustmentRequest,
    CommitRequest,
    BatchCommitRequest,
    BatchPreviewRequest,
    BatchTradeSearchRequest,
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
from .mappings import build_mapping_provider
from .config import BATCH_FILTER_FIELDS

storage_mode = "vertica_sim+adjustment_meta"
app = FastAPI(
    title="LiMon Adjustment Manager API",
    version="0.1.0",
    description=(
        "Version-scoped LiMon trade adjustments. Select a snapshot and use "
        "preview before commit. See "
        "`docs/api-testing-guide.md` for complete executable examples."
    ),
    openapi_tags=[
        {"name": "Snapshots and trades", "description": "Read one LiMon as-of date and version."},
        {"name": "Mappings", "description": "Controlled values read from manifest-selected Parquet."},
        {"name": "Adjustments", "description": "Impact, preview and durable business writes."},
        {"name": "Operations", "description": "Technical health and reconciliation."},
    ],
)
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
    allow_credentials=True,
)
repo = build_repository()
mapping_provider = build_mapping_provider()
service = AdjustmentService(repo, mapping_provider)
audit_actor = os.getenv("AUDIT_ACTOR", "local-user")


@app.exception_handler(RuntimeError)
def runtime_configuration_error(_request: Request, exc: RuntimeError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "code": "BACKEND_CONFIGURATION_ERROR"},
    )


@app.exception_handler(psycopg.Error)
def database_connection_error(_request: Request, exc: psycopg.Error):
    message = str(exc).casefold()
    if "password authentication failed" in message:
        code, detail = "DATABASE_AUTHENTICATION_FAILED", "PostgreSQL rejected the configured user or password."
    elif any(value in message for value in ("could not translate host name", "name or service not known", "nodename nor servname provided")):
        code, detail = "DATABASE_HOST_NOT_FOUND", "The PostgreSQL hostname cannot be resolved."
    elif any(value in message for value in ("network is unreachable", "no route to host")):
        code, detail = "DATABASE_NETWORK_UNREACHABLE", "The PostgreSQL host resolved, but this machine has no network route to it."
    elif "timeout" in message or "timed out" in message:
        code, detail = "DATABASE_CONNECTION_TIMEOUT", "The PostgreSQL connection timed out."
    elif "connection refused" in message:
        code, detail = "DATABASE_CONNECTION_REFUSED", "The PostgreSQL host refused the connection."
    else:
        code, detail = "DATA_STORE_UNAVAILABLE", "The configured data store is unavailable. Check the backend database URL and connectivity."
    return JSONResponse(status_code=503, content={"detail": detail, "code": code, "databaseSqlState": exc.sqlstate})


def audit(event, metadata, context=None, row_id=None):
    repo.record_action(event, audit_actor, metadata, context, row_id)


def fail(exc):
    """Translate internal failures without leaking storage implementation details."""
    status = (
        503
        if isinstance(exc, InfrastructureError)
        else 409
        if isinstance(exc, ConflictError)
        else 422
    )
    raise HTTPException(status, str(exc))


@app.get("/api/health", tags=["Operations"])
def health():
    result = {
        "status": "ok",
        "mode": storage_mode,
        "project": os.getenv("ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf"),
    }
    if hasattr(repo, "health"):
        result["storage"] = repo.health()
    result["simulatedFailurePoint"] = os.getenv("SIMULATED_FAILURE_POINT") or None
    return result


@app.get("/api/asofdates", tags=["Snapshots and trades"])
def dates():
    return repo.asofdates()


@app.get("/api/versions", tags=["Snapshots and trades"])
def versions(asofdate: str):
    result = repo.versions(asofdate)
    audit("DATE_SELECTED", {"asofdate": asofdate, "availableVersions": len(result)})
    return result


@app.get("/api/fo-systems", tags=["Snapshots and trades"])
def fo_systems(
    asofdate: str,
    asofdateflow: str,
):
    context = LimonContext(asofdate=asofdate, asofdateflow=asofdateflow)
    return repo.fo_systems(context)


@app.get("/api/trades/batch-filters", tags=["Snapshots and trades"])
def batch_filter_fields():
    return BATCH_FILTER_FIELDS


@app.post("/api/trades/batch-search", tags=["Snapshots and trades"])
def batch_trade_search(
    req: BatchTradeSearchRequest,
):
    unknown = set(req.filters) - set(BATCH_FILTER_FIELDS)
    if unknown:
        fail(DomainError(f'Unsupported batch filter "{sorted(unknown)[0]}".'))
    items, total = repo.batch_search(
        req.context, req.foSystem, req.filters, req.page, req.pageSize
    )
    return {"items": items, "total": total}


@app.get("/api/trades", tags=["Snapshots and trades"])
def trades(
    asofdate: str,
    asofdateflow: str,
    search: str = "",
    foSystem: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
):
    """Search only within one immutable LiMon snapshot version.

    Example: ``/api/trades?asofdate=2026-08-06&asofdateflow=...&search=OT-98&foSystem=Orchestrade``.
    Full-snapshot reads are deliberately not exposed because production output
    contains too many rows for an interactive UI.
    """
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


@app.get("/api/trades/{row_id}", tags=["Snapshots and trades"])
def detail(
    row_id: str,
    asofdate: str,
    asofdateflow: str,
):
    try:
        context = LimonContext(asofdate=asofdate, asofdateflow=asofdateflow)
        result = (
            repo.get_trade_detail(context, row_id)
            if hasattr(repo, "get_trade_detail")
            else repo.get_effective_trade(context, row_id)
        )
        audit("TRADE_VIEWED", {}, context, row_id)
        return result
    except (DomainError, ValueError) as exc:
        fail(exc)


@app.get("/api/trades/{row_id}/history", tags=["Snapshots and trades"])
def history(row_id: str):
    return repo.get_history(row_id)


@app.get("/api/trades/{row_id}/lineage", tags=["Snapshots and trades"])
def lineage(
    row_id: str,
    asofdate: str,
    asofdateflow: str,
):
    try:
        return repo.get_lineage(
            LimonContext(asofdate=asofdate, asofdateflow=asofdateflow), row_id
        )
    except (DomainError, ValueError) as exc:
        fail(exc)


@app.get("/api/adjustments/history", tags=["Adjustments"])
def global_history(
    asofdate: str = "",
    asofdateflow: str = "",
):
    return repo.get_global_history(asofdate, asofdateflow)


@app.get("/api/mappings/fields", tags=["Mappings"])
def mapped_fields():
    return mapping_provider.fields()


@app.get("/api/mappings/values", tags=["Mappings"])
def mapping_values(
    field: str,
    search: str = "",
    limit: int = Query(50, ge=1, le=200),
):
    try:
        return mapping_provider.values(field, search, limit)
    except DomainError as exc:
        fail(exc)


@app.get("/api/mappings/{mapping_name}/rows", tags=["Mappings"])
def mapping_rows(
    mapping_name: str,
    search: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
):
    try:
        return mapping_provider.rows(mapping_name, search, page, pageSize)
    except DomainError as exc:
        fail(exc)


@app.post("/api/adjustments/impact", tags=["Adjustments"])
def impact(req: AdjustmentRequest):
    return {"impactedStages": service.resolver.resolve(set(req.changes))}


@app.post("/api/adjustments/preview", tags=["Adjustments"])
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


@app.post("/api/adjustments/cancel/preview", tags=["Adjustments"])
def cancel_preview(req: CancelTradeRequest):
    try:
        return service.preview_cancellation(req.context, req.rowId)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/cancel/commit", tags=["Adjustments"])
def cancel_commit(
    req: CancelTradeCommitRequest,
):
    try:
        return service.commit_cancellation(req, audit_actor)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/proxy/preview", tags=["Adjustments"])
def proxy_preview(req: ProxyPreviewRequest):
    try:
        return service.preview_proxy(req.context, req.draftId, req.fields)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/proxy/commit", tags=["Adjustments"])
def proxy_commit(
    req: ProxyCommitRequest,
):
    try:
        return service.commit_proxy(req, audit_actor)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/commit", tags=["Adjustments"])
def commit(req: CommitRequest):
    try:
        return service.commit(req, audit_actor)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/batch/commit", tags=["Adjustments"])
def batch_commit(
    req: BatchCommitRequest,
):
    try:
        return service.commit_batch(req, audit_actor)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/batch/preview", tags=["Adjustments"])
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


@app.post("/api/adjustments/{batch_id}/revert", tags=["Adjustments"])
def revert_adjustment(
    batch_id: str,
    req: RevertAdjustmentRequest,
):
    try:
        return service.revert_adjustment(batch_id, req, audit_actor)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/{batch_reference}/reconcile", tags=["Operations"])
def reconcile_adjustment(
    batch_reference: str,
):
    try:
        return repo.reconcile_adjustment(batch_reference)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)
