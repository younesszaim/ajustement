# LiMon simple Streamlit prototype

For the complete architecture, file-by-file guide, API reference and sequence
diagrams, see `docs/streamlit-fastapi-architecture.md`.

This folder is a side-by-side replacement candidate for the React application
and its complex backend. A small FastAPI process owns calculations and storage;
Streamlit is only the HTTP UI. It intentionally has two durable storage objects:

1. the existing Vertica `output_completude_table`, containing BASE, REVERSAL
   and ADJUSTED business rows;
2. one PostgreSQL `adjustment_operations` table, containing the minimal user
   intention, status and generated output IDs.

The browser and Streamlit never connect to either database. Streamlit calls the
small API; the API calls `AdjustmentService` and the two storage classes.

## Current vertical slice

- calendar-based as-of selection and version/FO system/leg context;
- server-side active-row search, then client-side AG Grid filters;
- Cash (`leg_flag=0`) or Titre (`leg_flag=1`) amount adjustment;
- original/reversal/adjusted preview;
- append-only Vertica commit with idempotent retry;
- audited append-only revert of a committed replacement;
- global PostgreSQL operation register.

Cancel, revert, proxy creation and multi-trade commit are deliberately not in
this first validation slice. They should only be migrated after this smaller
model is accepted.

## Database preparation

Apply `migrations/001_adjustment_operations.sql` to PostgreSQL. Ask the Vertica
DBA to review and apply `sql/vertica_required_columns.sql`. `bi_id` is treated
as the unique ID for both original and generated rows. Change field/table names
only in `project.yaml`.

The configured calculation function is a demonstrator. Point
`calculation.callable` to the real LiMon function before production. Its
contract is:

```python
def recalculate(row: dict, columns: dict[str, str]) -> dict:
    # Return the complete recalculated row without changing its identity.
    return row
```

## Run entirely on Supabase

For development, Supabase can play both database roles. The existing
`vertica_sim.output_completude_table` is the simulated output and
`adjustment_simple.adjustment_operations` is the only runtime metadata table.
Apply these files in the Supabase SQL editor, in order:

1. `migrations/001_adjustment_operations.sql`
2. `migrations/002_supabase_output_lineage.sql`
3. `migrations/003_revert_operations.sql`

Then configure:

```dotenv
POSTGRES_URL=postgresql://...
POSTGRES_SCHEMA=adjustment_simple
OUTPUT_DATABASE=postgres
LIMON_PROJECT_CONFIG=streamlit_app/project.supabase.yaml
ADJUSTMENT_ACTOR=limon-user
```

No `VERTICA_*` variables are required in this mode. The small FastAPI process
is required because it now owns all database access and calculations.
When `SUPABASE_DB_URL` exists, the app automatically selects PostgreSQL output
mode and `project.supabase.yaml`. Restart Streamlit after changing environment
variables because its database services are cached for the process lifetime.
The application automatically loads `.env.streamlit` when present, otherwise
it loads the project `.env`; manually running `source` is optional.

## Run

```bash
python -m venv .venv-streamlit
.venv-streamlit/bin/pip install -r streamlit_app/requirements.txt
cp streamlit_app/.env.example .env.streamlit
set -a
source .env.streamlit
set +a
# Terminal 1: calculations, SQL and commits
PYTHONPATH=. .venv-streamlit/bin/uvicorn streamlit_app.api:app --reload --port 8001

# Terminal 2: UI only
PYTHONPATH=. .venv-streamlit/bin/streamlit run streamlit_app/app.py
```

Run the unit tests without a database:

```bash
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests -q
```

## Optional Flask learning adapter

The active UI normally uses FastAPI. An equivalent Flask HTTP adapter is also
available for framework comparison and reuses the same services and storage:

```bash
PYTHONPATH=. .venv/bin/flask --app streamlit_app.flask_api run --debug --port 8001
```

Its URLs and JSON match FastAPI, so Streamlit can use it through the same
`LIMON_API_URL`. Flask does not provide this project's automatic Swagger page.
See [the Flask learning guide](../docs/flask-api-learning-guide.md) for route
examples and a detailed comparison.

## Commit and recovery sequence

1. Preview re-reads the currently active output row.
2. Commit re-runs that same preview builder.
3. PostgreSQL records the intention as `PENDING` using a unique idempotency key.
4. Vertica appends one negative REVERSAL and one recalculated ADJUSTED row.
5. PostgreSQL becomes `COMMITTED` and records both generated IDs.
6. If the Vertica write fails, PostgreSQL becomes `FAILED`.
7. If Vertica succeeds but PostgreSQL confirmation fails, retrying the same
   intention detects its `adjustment_reference` in Vertica and only completes
   PostgreSQL; it does not insert duplicate output rows.

### Draft identity and safe retries

An idempotency key identifies one complete adjustment intention, not merely a
selected trade. Its identity includes the full context, source output ID,
applicable amount, every controlled field change, and the trimmed audit reason.

Streamlit stores a deterministic `draft_signature` for those inputs. Previewing
the same values keeps the existing `draft_key`; changing any value creates a
new key before preview. Commit always submits the immutable `preview_draft`, so
unsubmitted widget edits cannot alter a previously previewed result.

| Situation | Key behavior | Expected result | User action |
|---|---|---|---|
| First preview | Create a new key | Read-only preview | Review, then commit |
| Exact retry after timeout or uncertain response | Keep the key | Return/finish the same operation without duplicates | Retry Commit |
| Output insert fails before rows exist | Keep the key only while the draft is unchanged | PostgreSQL is `FAILED`; output has no generated pair | Fix output, then retry the identical draft |
| User changes amount, controlled field or reason after failure | Create a new key on the next Preview | New independent intention | Preview again, then commit |
| User changes context or selected row | Clear draft, signature, key and preview | Stale intention cannot be committed | Search/select and preview again |
| Output exists but PostgreSQL confirmation failed | Keep the key | Retry only confirms metadata | Retry the identical commit |
| Same key arrives with different content | Reject with HTTP 409 | No append and no old success returned | Preview the modified draft for a new key |
| Same key and operation is already `COMMITTED` | Keep the key | Existing success is returned | No further action |
| Source row became inactive before commit | Draft is stale | HTTP 409, no write | Refresh and adjust the current active row |

The backend validates the complete stored intention before both the `COMMITTED`
fast path and partial-failure reconciliation. A reused key therefore cannot
silently return an older success or confirm rows belonging to another draft.
