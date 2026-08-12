"""FastAPI composition root and HTTP boundary.

Endpoints in this module stay intentionally thin: authenticate, validate the
Pydantic request, call a domain service/repository, audit relevant reads, and
translate known failures to HTTP status codes. Business row construction must
remain in ``services.py`` so preview, single commit and batch commit share it.
"""

import os
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
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
from .auth import (
    BUSINESS_WRITE,
    MOCK_USERS,
    PREVIEW,
    READ,
    TECHNICAL_ADMIN,
    MockLoginRequest,
    auth_mode,
    clear_session,
    create_mock_session,
    current_identity,
    require,
)
from .mappings import build_mapping_provider

load_dotenv()
storage_mode = os.getenv("STORAGE_MODE", "supabase").lower()
app = FastAPI(
    title="LiMon Adjustment Manager API",
    version="0.1.0",
    description=(
        "Version-scoped LiMon trade adjustments. Start with **Authentication**, "
        "then select a snapshot and use preview before commit. See "
        "`docs/api-testing-guide.md` for complete executable examples."
    ),
    openapi_tags=[
        {"name": "Authentication", "description": "Mock SSO session lifecycle."},
        {"name": "Snapshots and trades", "description": "Read one LiMon as-of date and version."},
        {"name": "Mappings", "description": "Controlled values read from manifest-selected Parquet."},
        {"name": "Adjustments", "description": "Impact, preview and durable business writes."},
        {"name": "Operations", "description": "Technical health and hybrid reconciliation."},
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


def audit(event, metadata, identity, context=None, row_id=None):
    repo.record_action(
        event, identity.email, metadata, context, row_id
    )


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


@app.get("/api/auth/mock-users", tags=["Authentication"])
def mock_users():
    if auth_mode() != "mock":
        raise HTTPException(404, "Mock login is disabled.")
    return [
        {"username": username, **identity.public()}
        for username, identity in MOCK_USERS.items()
    ]


@app.post("/api/auth/mock-login", tags=["Authentication"])
def mock_login(req: MockLoginRequest, response: Response):
    return create_mock_session(response, req.username).public()


@app.get("/api/auth/me", tags=["Authentication"])
def authenticated_user(request: Request):
    return current_identity(request).public()


@app.post("/api/auth/logout", status_code=204, tags=["Authentication"])
def logout(response: Response):
    clear_session(response)


@app.get("/api/health", tags=["Operations"])
def health(identity=Depends(require(TECHNICAL_ADMIN))):
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


@app.get("/api/asofdates", tags=["Snapshots and trades"])
def dates(identity=Depends(require(READ))):
    return repo.asofdates()


@app.get("/api/versions", tags=["Snapshots and trades"])
def versions(asofdate: str, identity=Depends(require(READ))):
    result = repo.versions(asofdate)
    audit("DATE_SELECTED", {"asofdate": asofdate, "availableVersions": len(result)}, identity)
    return result


@app.get("/api/trades", tags=["Snapshots and trades"])
def trades(
    asofdate: str,
    asofdateflow: str,
    search: str = "",
    foSystem: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    identity=Depends(require(READ)),
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
            identity,
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
    identity=Depends(require(READ)),
):
    try:
        context = LimonContext(asofdate=asofdate, asofdateflow=asofdateflow)
        result = (
            repo.get_trade_detail(context, row_id)
            if hasattr(repo, "get_trade_detail")
            else repo.get_effective_trade(context, row_id)
        )
        audit("TRADE_VIEWED", {}, identity, context, row_id)
        return result
    except (DomainError, ValueError) as exc:
        fail(exc)


@app.get("/api/trades/{row_id}/history", tags=["Snapshots and trades"])
def history(row_id: str, identity=Depends(require(READ))):
    return repo.get_history(row_id)


@app.get("/api/trades/{row_id}/lineage", tags=["Snapshots and trades"])
def lineage(
    row_id: str,
    asofdate: str,
    asofdateflow: str,
    identity=Depends(require(READ)),
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
    identity=Depends(require(READ)),
):
    return repo.get_global_history(asofdate, asofdateflow)


@app.get("/api/mappings/fields", tags=["Mappings"])
def mapped_fields(identity=Depends(require(READ))):
    return mapping_provider.fields()


@app.get("/api/mappings/values", tags=["Mappings"])
def mapping_values(
    field: str,
    search: str = "",
    limit: int = Query(50, ge=1, le=200),
    identity=Depends(require(PREVIEW)),
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
    identity=Depends(require(READ)),
):
    try:
        return mapping_provider.rows(mapping_name, search, page, pageSize)
    except DomainError as exc:
        fail(exc)


@app.post("/api/adjustments/impact", tags=["Adjustments"])
def impact(req: AdjustmentRequest, identity=Depends(require(PREVIEW))):
    return {"impactedStages": service.resolver.resolve(set(req.changes))}


@app.post("/api/adjustments/preview", tags=["Adjustments"])
def preview(req: AdjustmentRequest, identity=Depends(require(PREVIEW))):
    try:
        result = service.preview(req.context, req.rowId, req.changes)
        audit(
            "PREVIEW_COMPLETED",
            {
                "changedFields": list(req.changes),
                "impactedStages": result["impactedStages"],
            },
            identity,
            req.context,
            req.rowId,
        )
        return result
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/cancel/preview", tags=["Adjustments"])
def cancel_preview(req: CancelTradeRequest, identity=Depends(require(PREVIEW))):
    try:
        return service.preview_cancellation(req.context, req.rowId)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/cancel/commit", tags=["Adjustments"])
def cancel_commit(
    req: CancelTradeCommitRequest,
    identity=Depends(require(BUSINESS_WRITE)),
):
    try:
        return service.commit_cancellation(req, identity.email)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/proxy/preview", tags=["Adjustments"])
def proxy_preview(req: ProxyPreviewRequest, identity=Depends(require(PREVIEW))):
    try:
        return service.preview_proxy(req.context, req.draftId, req.fields)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/proxy/commit", tags=["Adjustments"])
def proxy_commit(
    req: ProxyCommitRequest,
    identity=Depends(require(BUSINESS_WRITE)),
):
    try:
        return service.commit_proxy(req, identity.email)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/commit", tags=["Adjustments"])
def commit(req: CommitRequest, identity=Depends(require(BUSINESS_WRITE))):
    try:
        return service.commit(req, identity.email)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/batch/commit", tags=["Adjustments"])
def batch_commit(
    req: BatchCommitRequest,
    identity=Depends(require(BUSINESS_WRITE)),
):
    try:
        return service.commit_batch(req, identity.email)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/batch/preview", tags=["Adjustments"])
def batch_preview(req: BatchPreviewRequest, identity=Depends(require(PREVIEW))):
    try:
        result = service.preview_batch(req.context, req.items)
        audit(
            "PREVIEW_COMPLETED",
            {
                "batch": True,
                "tradeCount": result["tradeCount"],
                "impactedStages": result["impactedStages"],
            },
            identity,
            req.context,
        )
        return result
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/{batch_id}/revert", tags=["Adjustments"])
def revert_adjustment(
    batch_id: str,
    req: RevertAdjustmentRequest,
    identity=Depends(require(BUSINESS_WRITE)),
):
    try:
        return service.revert_adjustment(batch_id, req, identity.email)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)


@app.post("/api/adjustments/{batch_reference}/reconcile", tags=["Operations"])
def reconcile_adjustment(
    batch_reference: str,
    identity=Depends(require(TECHNICAL_ADMIN)),
):
    try:
        if not hasattr(repo, "reconcile_adjustment"):
            raise InfrastructureError(
                "Reconciliation is available only in hybrid storage mode."
            )
        return repo.reconcile_adjustment(batch_reference)
    except (DomainError, InfrastructureError) as exc:
        fail(exc)
