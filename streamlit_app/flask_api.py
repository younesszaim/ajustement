"""Educational Flask HTTP adapter for the LiMon adjustment domain.

This module is intentionally parallel to :mod:`streamlit_app.api`.  It reuses
the same Pydantic request contracts, runtime, services, stores and preview job
manager; only the web-framework adapter changes.  The production prototype can
therefore stay on FastAPI while developers compare both styles safely.
"""

from __future__ import annotations

from dataclasses import asdict

from flask import Flask, jsonify, request
from pydantic import ValidationError

from .api_models import AdjustmentBody, RevertBody
from .jobs import PreviewJobManager
from .models import AdjustmentDraft, Context
from .runtime import build_runtime
from .service import AdjustmentError


def _domain_input(body: AdjustmentBody) -> tuple[Context, AdjustmentDraft]:
    """Translate an HTTP contract into framework-independent domain objects."""
    return (
        Context(**body.context.model_dump()),
        AdjustmentDraft(
            source_output_id=body.source_output_id,
            new_amount=body.new_amount,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
            changes=body.changes,
        ),
    )


def _validation_error(exc: ValidationError):
    """Return FastAPI-like HTTP 422 details for malformed Flask requests."""
    return jsonify(
        detail=exc.errors(include_url=False, include_context=False)
    ), 422


def create_app(runtime_builder=build_runtime, preview_manager=None) -> Flask:
    """Create an injectable Flask application.

    Passing a runtime stub makes route tests database-free.  In normal use the
    default builder creates exactly the same stores and service as FastAPI.
    """
    flask_app = Flask(__name__)
    jobs = preview_manager or PreviewJobManager()

    def runtime():
        try:
            return runtime_builder()
        except Exception:
            # Configuration details can contain hosts or driver information;
            # keep the public response deliberately generic.
            return None

    @flask_app.get("/health")
    def health():
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        settings, *_ = dependencies
        return jsonify(
            status="ok",
            outputDatabase=settings.output_database,
            outputSchema=settings.project["output_schema"],
            outputTable=settings.project["output_table"],
        )

    @flask_app.get("/contexts/asofdates")
    def asofdates():
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        _, output, *_ = dependencies
        try:
            return jsonify(items=output.context_values("asofdate"))
        except Exception:
            return jsonify(detail="The output data source is unavailable"), 503

    @flask_app.get("/contexts/versions")
    def versions():
        asofdate = request.args.get("asofdate", "").strip()
        if not asofdate:
            return jsonify(detail="Query parameter 'asofdate' is required"), 422
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        _, output, *_ = dependencies
        try:
            return jsonify(items=output.context_values("version", {"asofdate": asofdate}))
        except Exception:
            return jsonify(detail="The output data source is unavailable"), 503

    @flask_app.get("/contexts/fo-systems")
    def fo_systems():
        asofdate = request.args.get("asofdate", "").strip()
        version = request.args.get("version", "").strip()
        if not asofdate or not version:
            return jsonify(detail="Query parameters 'asofdate' and 'version' are required"), 422
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        _, output, *_ = dependencies
        try:
            return jsonify(
                items=output.context_values(
                    "fo_system", {"asofdate": asofdate, "version": version}
                )
            )
        except Exception:
            return jsonify(detail="The output data source is unavailable"), 503

    @flask_app.get("/trades")
    def trades():
        required = {
            key: request.args.get(key, "").strip()
            for key in ("asofdate", "version", "fo_system")
        }
        try:
            leg_flag = int(request.args.get("leg_flag", ""))
            limit = int(request.args.get("limit", "500"))
        except ValueError:
            return jsonify(detail="'leg_flag' and 'limit' must be integers"), 422
        if not all(required.values()) or leg_flag not in (0, 1) or not 1 <= limit <= 2000:
            return jsonify(
                detail="A full context is required; leg_flag is 0/1 and limit is 1..2000"
            ), 422
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        _, output, *_ = dependencies
        context = Context(**required, leg_flag=leg_flag)
        try:
            items = output.search_active(context, request.args.get("search", ""), limit)
            return jsonify(items=items, returned=len(items), limit=limit)
        except Exception:
            return jsonify(detail="Trade search failed"), 503

    def adjustment_request():
        """Parse one JSON body with the contracts shared with FastAPI."""
        try:
            return AdjustmentBody.model_validate(request.get_json(silent=True) or {})
        except ValidationError as exc:
            return _validation_error(exc)

    @flask_app.post("/adjustments/preview")
    def preview():
        body = adjustment_request()
        if isinstance(body, tuple):
            return body
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        *_, service = dependencies
        context, draft = _domain_input(body)
        try:
            return jsonify(asdict(service.preview(context, draft)))
        except AdjustmentError as exc:
            return jsonify(detail=str(exc)), 409
        except Exception:
            return jsonify(detail="Preview calculation failed"), 503

    @flask_app.post("/adjustments/preview-jobs")
    def start_preview_job():
        body = adjustment_request()
        if isinstance(body, tuple):
            return body
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        settings, _, _, service = dependencies
        context, draft = _domain_input(body)
        job = jobs.submit(
            lambda progress: asdict(
                service.preview(
                    context,
                    draft,
                    progress_callback=progress,
                    delay_seconds=settings.simulated_calculation_delay_seconds,
                )
            )
        )
        return jsonify(job), 202

    @flask_app.get("/adjustments/preview-jobs/<job_id>")
    def preview_job_status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            return jsonify(detail="Preview job was not found or has expired"), 404
        return jsonify(job)

    @flask_app.post("/adjustments/commit")
    def commit():
        body = adjustment_request()
        if isinstance(body, tuple):
            return body
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        *_, service = dependencies
        context, draft = _domain_input(body)
        try:
            return jsonify(service.commit(context, draft))
        except AdjustmentError as exc:
            return jsonify(detail=str(exc)), 409
        except Exception:
            return jsonify(detail="Adjustment commit failed"), 503

    @flask_app.get("/adjustments")
    def adjustments():
        try:
            limit = int(request.args.get("limit", "1000"))
        except ValueError:
            return jsonify(detail="'limit' must be an integer"), 422
        if not 1 <= limit <= 1000:
            return jsonify(detail="'limit' must be between 1 and 1000"), 422
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        _, _, operations, _ = dependencies
        try:
            return jsonify(items=operations.list_recent(limit))
        except Exception:
            return jsonify(detail="Adjustment register is unavailable"), 503

    @flask_app.post("/adjustments/<operation_id>/revert")
    def revert_adjustment(operation_id: str):
        try:
            body = RevertBody.model_validate(request.get_json(silent=True) or {})
        except ValidationError as exc:
            return _validation_error(exc)
        dependencies = runtime()
        if dependencies is None:
            return jsonify(detail="Database configuration is unavailable"), 503
        *_, service = dependencies
        try:
            return jsonify(service.revert(operation_id, body.reason, body.idempotency_key))
        except AdjustmentError as exc:
            return jsonify(detail=str(exc)), 409
        except Exception:
            return jsonify(detail="Adjustment revert failed"), 503

    return flask_app


# Flask's CLI imports this conventional module-level object. Tests should use
# create_app() with injected dependencies instead of touching real databases.
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)
