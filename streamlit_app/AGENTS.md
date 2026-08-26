# Streamlit + FastAPI application agent guide

The root `AGENTS.md` applies. This file is the operational contract for the
active simplified application under `streamlit_app/`. Read it completely before
changing code here. Also read `docs/streamlit-fastapi-architecture.md` when a
request touches more than one layer.

## Product and architecture

The application lets one user select an exact output context, find an active
trade, preview an adjustment, commit an append-only journal pair, cancel a trade
with one reversal, inspect the register, and revert committed adjustments or
cancellations through an audited journal.

```text
Streamlit app.py
  -> client.py (HTTP only)
  -> api.py + api_models.py
  -> service.py + models.py
  -> calculations.py / storage.py
  -> Vertica output table + PostgreSQL adjustment_operations
```

Supabase development mode uses PostgreSQL for both physical connections, but
the logical boundary remains two stores:

- `vertica_sim.output_completude_table` simulates the append-only output;
- `adjustment_simple.adjustment_operations` is the only metadata table.

Do not import storage, calculations, or database drivers from Streamlit. Do not
put SQL in routes or business row construction in UI code.

## Non-negotiable business invariants

- Context is exactly `asofdate + version + fo_system + leg_flag`.
- `leg_flag=0` adjusts `cash_amount_eur`; `leg_flag=1` adjusts
  `security_amount_eur`. Leg is context, never an editable field.
- Output facts are append-only. Never `UPDATE` or `DELETE` output rows.
- Replacement commit appends `-original` REVERSAL plus recalculated ADJUSTED.
- Cancellation appends only `-active` REVERSAL and leaves no active row.
- Reverting cancellation appends only a restored ADJUSTED copy.
- Revert appends `-active adjusted` REVERSAL plus restored original values.
- Revert marks metadata status; it never erases the original operation.
- Preview and commit share `AdjustmentService._build_rows()`.
- Commit must re-read the active row. Never commit a UI-provided full row.
- A retry reuses the same idempotency key. Generated IDs are deterministic:
  `REV-{key}` and `ADJ-{key}`.
- Reversal negates every configured additive physical column and preserves all
  non-additive business columns.
- The output ID, parent ID, source ID, record type, and adjustment reference
  preserve lineage. Changing their meaning requires tests and documentation.
- Controlled values are configured in YAML and validated again by the service.
- A no-op draft is rejected even when a reason is provided.
- The operation table and output database cannot share a transaction. Preserve
  the existing idempotent recovery order and error behavior.

## File ownership and dependency rules

| File | Owns | Must not own |
|---|---|---|
| `app.py` | Streamlit widgets, dialogs, session state, display and polling | SQL, accounting rules, reversal construction |
| `client.py` | Every HTTP call made by Streamlit and user-safe transport errors | Streamlit widgets or domain calculations |
| `api.py` | Thin routes, dependency calls, HTTP status translation | SQL or duplicated service logic |
| `flask_api.py` | Optional educational Flask adapter with the same HTTP contract | Duplicated domain/storage rules |
| `api_models.py` | Pydantic request bodies and HTTP validation | Database models or calculations |
| `models.py` | Framework-independent domain dataclasses | HTTP, SQL, Streamlit |
| `service.py` | Context validation, journal building, idempotency, commit/revert workflows | Concrete SQL or UI messages/layout |
| `calculations.py` | Ordered DataFrame stages and progress callbacks | Database access, HTTP, Streamlit |
| `jobs.py` | In-memory preview execution and pollable job state | Durable audit history or business calculations |
| `storage.py` | Parameterized SQL and database transactions | FastAPI exceptions or UI behavior |
| `runtime.py` | Dependency construction and database-mode selection | Business decisions |
| `config.py` | Environment loading and YAML-to-Settings conversion | Secrets or project-specific Python constants |
| `project*.yaml` | Semantic keys, physical names, labels, controlled options, additive fields | Credentials |

Dependencies flow downward only. Use constructor injection and repository fakes
in tests instead of importing runtime globals into the domain service.

## Semantic field configuration

Python code uses stable semantic keys such as `output_id`, `isin`,
`cash_amount_eur`, and `exposure_class`. Physical names belong only in
`project.yaml` and `project.supabase.yaml`.

When adding a displayed field:

1. Add the semantic key to `fields` in both relevant YAML configurations.
2. Set its real and simulated physical column names independently.
3. Add the key to `display_fields`.
4. Ensure the simulated table actually contains the configured column.
5. Add a configuration/storage regression test.

When adding an adjustable field:

1. Complete the displayed-field steps.
2. Add it to `editable_fields` with its reviewed options.
3. Decide which calculation stage produces or consumes it.
4. Update `CalculationPipeline` dependency routing.
5. Test valid, invalid, unchanged, and downstream recalculation behavior.

When adding an amount-like output, explicitly decide whether reversal must
negate it. Prefer `additive: true`; use a reviewed regex pattern only for a
well-defined family. Never infer additivity from Python code or UI labels.

## Calculation pipeline contract

The configured callable receives:

```python
def recalculate(
    row: dict,
    columns: dict[str, str],
    overrides: dict[str, object],
    progress_callback=None,
    delay_seconds: float = 0.0,
) -> tuple[dict, list[str]]:
    ...
```

- Functions operate on and return complete pandas DataFrames.
- `CalculationPipeline.stages` is the reviewed execution order; do not use
  reflection or alphabetical method discovery.
- A manually supplied stage output starts after its producing stage.
- A changed input starts at the stage that consumes it.
- Multiple changes start at the earliest required stage.
- Reapply manual overrides after every downstream stage so later calculations
  cannot silently replace explicit user choices.
- Preserve row count. A stage that adds/removes rows must be a separate,
  deliberately designed workflow.
- Call the progress callback before and after each stage. Calculation code must
  remain unaware of FastAPI, jobs, or Streamlit.
- `SIMULATED_CALCULATION_DELAY_SECONDS` is development-only and must default to
  zero in production.

## Preview job behavior

Streamlit starts `POST /adjustments/preview-jobs`, then polls
`GET /adjustments/preview-jobs/{job_id}`. Terminal states are `COMPLETED` and
`FAILED`. Preserve the synchronous preview endpoint for direct Swagger tests.

The current manager is process-local and appropriate only for one API process.
Do not enable multiple Uvicorn workers without replacing it with shared state.
Never store job progress in `adjustment_operations`; progress is transient,
whereas that table is durable audit metadata.

## Streamlit state and UI rules

- Remember that every widget interaction reruns `app.py` top to bottom.
- Server results come from the API; temporary selection/draft/preview lives in
  `st.session_state`.
- Context change clears search results, selected row, preview, and draft key.
- Selected-row change clears stale preview and creates a new draft intention.
- Field or amount change requires a new preview before commit.
- Preserve the draft and stable idempotency key after uncertain commit failure.
- Treat context, source row, amount, controlled changes and trimmed reason as
  the complete draft identity. A modified draft gets a new key at Preview;
  an exact retry keeps the existing key.
- Validate a stored retry intention before any COMMITTED fast path or output
  reconciliation. Never return an older success for changed request content.
- Search remains server-bounded; AG Grid may refine only returned rows.
- Show original, reversal, and adjusted separately and label them clearly.
- Destructive revert is red, requires a reason, and is located beside Review.
- Display API failures visibly; never replace an error with an empty result.
- Use native Streamlit components before custom HTML/CSS.

## HTTP and error behavior

- Add every Streamlit API call to `AdjustmentApiClient`; do not scatter
  `httpx` calls through `app.py`.
- Business conflicts use `AdjustmentError` and HTTP 409.
- Missing preview jobs use HTTP 404.
- Configuration/storage failures use HTTP 503 with safe messages.
- Pydantic owns malformed request HTTP 422 responses.
- Never expose SQL, database URLs, credentials, or stack traces.
- A new route needs a Swagger-friendly docstring/example, a client method when
  used by Streamlit, and an API test.

## Storage and lineage model

For a base row `BASE-1`, replacement key `K1` creates:

```text
BASE-1
├── REV-K1  parent=BASE-1, source=BASE-1, amount=-original
└── ADJ-K1  parent=BASE-1, source=BASE-1, amount=new value
```

The active-row query returns BASE/ADJUSTED rows only when no configured
REVERSAL points to that row as parent. A revert key `K2` points its reversal
and restored row at the active `ADJ-K1`, while retaining the original source.

All SQL identifiers originate from reviewed configuration and are quoted by
`_identifier()`. All data values use `%s` parameters. Preserve transaction
commit/rollback behavior in `append()` and metadata updates.

## Common change playbooks

### Add an endpoint

1. Define/extend domain dataclasses and Pydantic body.
2. Implement behavior in service or store, not route.
3. Add thin route and safe error translation.
4. Add client method if the UI consumes it.
5. Add service/API tests, Swagger example, and architecture documentation.

### Fix a UI/API bug

1. Reproduce and capture the actual request, response, and state transition.
2. Identify the owning layer instead of masking it in Streamlit.
3. Add the smallest regression test.
4. Fix while preserving draft/idempotency behavior.
5. Verify both success and failure display without refreshing the page.

### Add a durable operation

1. Define journal rows and which row becomes active.
2. Define idempotency and deterministic output IDs.
3. Define partial-failure/retry behavior across both databases.
4. Extend the forward-only migration and operation store.
5. Implement service preview/commit using shared builders.
6. Add register/review behavior and end-to-end tests.

## Commands and verification

```bash
# Focused unit suite; does not require a database
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests -q

# One file or test while iterating
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests/test_service.py -q
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests/test_service.py::test_name -q

# API
PYTHONPATH=. .venv/bin/uvicorn streamlit_app.api:app --reload --port 8001

# Optional Flask adapter for comparison (run instead of FastAPI)
PYTHONPATH=. .venv/bin/flask --app streamlit_app.flask_api run --debug --port 8001

# UI in another terminal
PYTHONPATH=. .venv/bin/streamlit run streamlit_app/app.py
```

Also run `make check` when edits can affect the retained legacy application.
Never make real commits/reverts merely to test presentation. Prefer fakes and
preview-only API calls; clearly warn before any test that writes shared data.

## Definition of done

- Change lives in the owning layer and does not duplicate another layer.
- Append-only, context, lineage, recalculation, and idempotency invariants hold.
- Happy path plus relevant no-op, invalid, stale, retry, and failure paths are
  tested.
- Streamlit exposes loading, empty, error, success, and retry states.
- Both YAML modes remain valid when field/config contracts change.
- Focused Streamlit tests pass; broader checks pass when applicable.
- Documentation and `.env.example` reflect new endpoints or settings.
- Handoff says whether database migrations/writes and git commit/push occurred.

## Prohibited patterns

- Direct database access from Streamlit.
- Direct HTTP calls outside `client.py`.
- SQL in `api.py` or `service.py`.
- Reversal/adjusted construction in UI or route code.
- Physical deletion or update of output facts.
- Fresh idempotency keys on retries.
- Hard-coded physical business columns in Python.
- Loading an entire snapshot into AG Grid.
- Hiding API errors as empty tables.
- Running multiple API workers with the in-memory preview manager.
- Editing legacy React/FastAPI code to mirror a Streamlit-only change.
