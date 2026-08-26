# LiMon API in Flask — learning guide

## Purpose

`streamlit_app/flask_api.py` is an educational HTTP adapter. It does **not**
replace the current FastAPI adapter and does not duplicate adjustment rules.
Both frameworks call the same layers:

```text
Streamlit / curl
    -> FastAPI api.py OR Flask flask_api.py
    -> api_models.py (Pydantic request contracts)
    -> service.py (preview, commit, idempotency, revert)
    -> storage.py
    -> output database + PostgreSQL metadata
```

This separation is the main architectural lesson: Flask and FastAPI decide how
HTTP enters and leaves the application; `AdjustmentService` decides what an
adjustment means.

## Run the Flask version

Load the same environment variables used by FastAPI, then run one of:

```bash
# Development server with automatic reload
PYTHONPATH=. .venv/bin/flask --app streamlit_app.flask_api run --debug --port 8001

# Equivalent direct Python entry point
PYTHONPATH=. .venv/bin/python -m streamlit_app.flask_api
```

Point Streamlit to it without changing frontend code:

```bash
LIMON_API_URL=http://127.0.0.1:8001 \
PYTHONPATH=. .venv/bin/streamlit run streamlit_app/app.py
```

Do not run FastAPI and Flask on the same port. To compare them simultaneously,
keep FastAPI on `8001`, run Flask on `8002`, and change `LIMON_API_URL`.

The built-in Flask server is for learning and local development, not production.

## File structure

### `create_app()`

The application factory creates and configures a new Flask instance:

```python
app = create_app()
```

It accepts an optional `runtime_builder`. Tests inject a stub runtime, while
normal execution uses `build_runtime()` and real configured stores. This avoids
opening databases in route unit tests.

### Module-level `app`

Flask's CLI expects an importable application object. The final module-level
`app = create_app()` provides it, while tests remain free to build isolated
instances.

### Shared request models

FastAPI calls Pydantic automatically. Flask does not know about Pydantic, so the
adapter performs the call explicitly:

```python
body = AdjustmentBody.model_validate(request.get_json(silent=True) or {})
```

A `ValidationError` is translated into HTTP `422` with a `detail` list. Valid
models are converted into the same framework-independent `Context` and
`AdjustmentDraft` dataclasses used by FastAPI.

### Error translation

| Python outcome | Flask response |
|---|---|
| Pydantic `ValidationError` | `422` plus field details |
| `AdjustmentError` | `409` plus safe business explanation |
| Missing preview job | `404` |
| Database/configuration/infrastructure exception | `503` plus generic message |
| Successful creation of preview job | `202` |

SQL errors, credentials, hosts and tracebacks are never returned to clients.

### Background preview

Flask and FastAPI share `PreviewJobManager`. `POST /adjustments/preview-jobs`
submits the calculation and returns immediately; the UI polls the job URL.
The manager remains process-local, so the same single-worker limitation applies
to both adapters.

## Route equivalence

| Method and path | Flask function | Domain/store call |
|---|---|---|
| `GET /health` | `health()` | Runtime configuration only |
| `GET /contexts/asofdates` | `asofdates()` | `output.context_values()` |
| `GET /contexts/versions` | `versions()` | `output.context_values()` |
| `GET /contexts/fo-systems` | `fo_systems()` | `output.context_values()` |
| `GET /trades` | `trades()` | `output.search_active()` |
| `POST /adjustments/preview` | `preview()` | `service.preview()` |
| `POST /adjustments/preview-jobs` | `start_preview_job()` | `PreviewJobManager.submit()` |
| `GET /adjustments/preview-jobs/<job_id>` | `preview_job_status()` | `PreviewJobManager.get()` |
| `POST /adjustments/commit` | `commit()` | `service.commit()` |
| `POST /adjustments/cancel` | `cancel_trade()` | `service.commit_cancel()` |
| `GET /adjustments` | `adjustments()` | `operations.list_recent()` |
| `POST /adjustments/<operation_id>/revert` | `revert_adjustment()` | `service.revert()` |

The URL and JSON contracts match the FastAPI version, so
`AdjustmentApiClient` works with either server.

## Requests to try

### Health

```bash
curl http://127.0.0.1:8001/health
```

### Context and trade search

```bash
curl "http://127.0.0.1:8001/contexts/versions?asofdate=2026-08-06"

curl --get http://127.0.0.1:8001/trades \
  --data-urlencode "asofdate=2026-08-06" \
  --data-urlencode "version=2026-08-07T11:14:09" \
  --data-urlencode "fo_system=Murex" \
  --data-urlencode "leg_flag=0" \
  --data-urlencode "search=T-100"
```

### Preview

Preview is read-only. Replace the example context and row ID with values from
the search response:

```bash
curl -X POST http://127.0.0.1:8001/adjustments/preview \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "asofdate": "2026-08-06",
      "version": "2026-08-07T11:14:09",
      "fo_system": "Murex",
      "leg_flag": 0
    },
    "source_output_id": "ROW-1",
    "new_amount": 250.0,
    "reason": "Correct the classified amount",
    "idempotency_key": "learning-preview-1",
    "changes": {"exposure_class": "CORPORATE"}
  }'
```

`POST /adjustments/commit` accepts the same body but writes data. Do not use it
against shared or production-like data merely to learn the route.

## FastAPI versus Flask in this project

| Concern | FastAPI | Flask adapter |
|---|---|---|
| Route declaration | `@app.get()` / `@app.post()` | Same decorator style |
| Body validation | Automatic from type annotation | Explicit `model_validate()` |
| Query validation | Automatic with `Query` | Explicit parsing and bounds checks |
| JSON response | Return dict/dataclass-compatible value | Call `jsonify()` |
| Status/error response | Raise `HTTPException` | Return `(jsonify(...), status)` |
| OpenAPI/Swagger | Automatic at `/docs` | Not included in this educational adapter |
| Dependency injection | Functions call `runtime()` | Factory closure calls injected runtime builder |
| Business behavior | Shared `AdjustmentService` | Shared `AdjustmentService` |

FastAPI is more concise for typed APIs and generates interactive documentation.
Flask makes the HTTP mechanics explicit, which is useful for learning. Neither
framework should contain SQL, reversal construction, recalculation rules or
idempotency decisions.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests/test_flask_api.py -q
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests -q
```

`test_flask_api.py` demonstrates the application-factory pattern, a database-free
runtime stub, contract-compatible success responses, manual HTTP 422 validation,
business HTTP 409 conflicts, and safe HTTP 503 configuration errors.
