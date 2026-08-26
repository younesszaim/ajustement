"""Small HTTP boundary for Streamlit and future clients."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query

from .api_models import AdjustmentBody, CancellationBody, RevertBody
from .jobs import PreviewJobManager
from .models import AdjustmentDraft, CancellationDraft, Context
from .runtime import build_runtime
from .service import AdjustmentError


app = FastAPI(title="LiMon Simple Adjustment API", version="0.1.0")

# One manager belongs to one API process. This is intentionally simple for the
# single-user prototype; multi-worker production must use shared durable state.
preview_jobs = PreviewJobManager()


def runtime():
    """Resolve cached services and translate startup failures to HTTP 503."""
    try:
        return build_runtime()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database configuration is unavailable: {exc}") from exc


def domain_input(body: AdjustmentBody):
    """Convert validated HTTP models into framework-independent dataclasses."""
    context = Context(**body.context.model_dump())
    draft = AdjustmentDraft(
        source_output_id=body.source_output_id,
        new_amount=body.new_amount,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        changes=body.changes,
    )
    return context, draft


@app.get("/health")
def health():
    """Report the configured output mode without querying a business table."""
    settings, *_ = runtime()
    return {
        "status": "ok",
        "outputDatabase": settings.output_database,
        "outputSchema": settings.project["output_schema"],
        "outputTable": settings.project["output_table"],
    }


@app.get("/contexts/asofdates")
def asofdates():
    """Return distinct output dates for the Streamlit calendar."""
    _, output, *_ = runtime()
    try:
        return {"items": output.context_values("asofdate")}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The output data source is unavailable") from exc


@app.get("/contexts/versions")
def versions(asofdate: str):
    """Return versions that exist for one selected as-of date."""
    _, output, *_ = runtime()
    try:
        return {"items": output.context_values("version", {"asofdate": asofdate})}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The output data source is unavailable") from exc


@app.get("/contexts/fo-systems")
def fo_systems(asofdate: str, version: str):
    """Return FO systems available inside one date/version snapshot."""
    _, output, *_ = runtime()
    try:
        return {
            "items": output.context_values(
                "fo_system", {"asofdate": asofdate, "version": version}
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The output data source is unavailable") from exc


@app.get("/trades")
def trades(
    asofdate: str,
    version: str,
    fo_system: str,
    leg_flag: int = Query(ge=0, le=1),
    search: str = "",
    limit: int = Query(default=500, ge=1, le=2000),
):
    """Search active rows on the database server and enforce a result limit.

    Example: ``?fo_system=Murex&leg_flag=1&search=ABC`` searches Titre rows
    for a trade number or ISIN containing ``ABC``.
    """
    _, output, *_ = runtime()
    context = Context(asofdate, version, fo_system, leg_flag)
    try:
        items = output.search_active(context, search, limit)
        return {"items": items, "returned": len(items), "limit": limit}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Trade search failed") from exc


@app.post("/adjustments/preview")
def preview(body: AdjustmentBody):
    """Build original/reversal/adjusted rows without writing either database."""
    *_, service = runtime()
    context, draft = domain_input(body)
    try:
        return asdict(service.preview(context, draft))
    except AdjustmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Preview calculation failed") from exc


@app.post("/adjustments/preview-jobs", status_code=202)
def start_preview_job(body: AdjustmentBody):
    """Start a background preview and immediately return its polling identity."""
    settings, _, _, service = runtime()
    context, draft = domain_input(body)

    # The closure contains the already validated domain input. The job manager
    # supplies only its progress callback when a worker thread starts running.
    return preview_jobs.submit(
        lambda progress: asdict(
            service.preview(
                context,
                draft,
                progress_callback=progress,
                delay_seconds=settings.simulated_calculation_delay_seconds,
            )
        )
    )


@app.get("/adjustments/preview-jobs/{job_id}")
def preview_job_status(job_id: str):
    """Return the latest stage, progress percentage and eventual preview."""
    job = preview_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Preview job was not found or has expired")
    return job


@app.post("/adjustments/commit")
def commit(body: AdjustmentBody):
    """Commit the same row construction used by preview."""
    *_, service = runtime()
    context, draft = domain_input(body)
    try:
        return service.commit(context, draft)
    except AdjustmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Adjustment commit failed") from exc


@app.post("/adjustments/cancel")
def cancel_trade(body: CancellationBody):
    """Cancel one active trade by appending a single audited reversal.

    Example body::

        {
          "context": {"asofdate": "2026-08-06", "version": "v1",
                      "fo_system": "Murex", "leg_flag": 0},
          "source_output_id": "ROW-1",
          "reason": "Trade cancelled by the source owner",
          "idempotency_key": "one-uuid-for-this-exact-cancellation"
        }

    The route never updates or deletes the source row and does not append an
    adjusted replacement. An exact retry reuses the same idempotency key.
    """
    *_, service = runtime()
    context = Context(**body.context.model_dump())
    draft = CancellationDraft(
        source_output_id=body.source_output_id,
        reason=body.reason.strip(),
        idempotency_key=body.idempotency_key,
    )
    try:
        return service.commit_cancel(context, draft)
    except AdjustmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Trade cancellation failed") from exc


@app.get("/adjustments")
def adjustments(limit: int = Query(default=1000, ge=1, le=1000)):
    """Return recent operation metadata for the grouped register."""
    _, _, operations, _ = runtime()
    try:
        return {"items": operations.list_recent(limit)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Adjustment register is unavailable") from exc


@app.post("/adjustments/{operation_id}/revert")
def revert_adjustment(operation_id: str, body: RevertBody):
    """Append an audited reversal/restoration for one committed replacement."""
    *_, service = runtime()
    try:
        return service.revert(operation_id, body.reason, body.idempotency_key)
    except AdjustmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Adjustment revert failed") from exc
