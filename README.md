# LiMon Adjustment Manager

An internal Finance workspace for version-scoped LiMon trade adjustments. It searches an exact `asofdate` + `asofdateflow`, previews dependency-aware recalculation, and records every change as an append-only cancellation plus replacement pair. Original production facts are never updated.

## Architecture

```text
React / TypeScript
        │ REST
        ▼
     FastAPI
        │
 ┌──────┼──────────────┐
 ▼      ▼              ▼
Trade  Dependency   Adjustment
repo   resolver     service
                      │
                      ▼
               LiMon calculations
                      │
                      ▼
                   Vertica
```

The application supports Supabase-only storage, a two-schema hybrid simulator, and a real Vertica/PostgreSQL adapter boundary. The in-memory repository is retained only as an isolated automated-test fixture. Business calculations still live behind `MockCalculationAdapter` until the production LiMon functions are connected through `backend/app/adapters/limon_calculation_adapter.py`.

## Run locally

Requires Node 18+ and Python 3.11+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
SUPABASE_DB_URL='postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require' uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The API is at `http://localhost:8000/docs`.

For ready-to-use Swagger and `curl` examples for every route, see
[docs/api-testing-guide.md](docs/api-testing-guide.md).

Local development uses mock SSO by default. Choose one of four identities on
the login page: reader, functional administrator, technical administrator, or
an authenticated user without application access. Sessions are signed and
stored in an HTTP-only cookie.

## Test and build

```bash
cd backend && PYTHONPATH=. pytest
cd frontend && npm run build
```

## Adjustment accounting

For the currently effective row, preview and commit both rebuild the journal authoritatively:

1. Clone the effective row as `ADJUSTMENT_CANCEL` and negate only configured additive measures.
2. Apply whitelisted input changes to a clone.
3. Resolve the transitive calculation DAG and run affected stages in topological order.
4. Store the recalculated clone as `ADJUSTMENT_REPLACEMENT`.
5. On commit, re-read the effective row and compare its deterministic version hash.
6. Insert both records plus audit metadata in one Vertica transaction; rollback everything on failure.

The mock repository mirrors atomicity, idempotency, effective-state lookup, and history in memory. Preview has no write side effects.

## Configuration and production integration

- Editable inputs: `backend/app/config.py` → `EDITABLE_FIELDS`
- Additive measures: `backend/app/config.py` → `ADDITIVE_MEASURES`
- Dependency graph: `FIELD_DEPENDENCIES` and `STAGE_DEPENDENCIES`
- Authentication: `AUTH_MODE=mock` enables development identities. Set a long
  random `AUTH_SESSION_SECRET`; it is a backend-only secret.
- Runtime storage: `SUPABASE_DB_URL` must be set as a backend secret. FastAPI has no mock-storage runtime switch.
- Vertica: provide `VERTICA_HOST`, `VERTICA_PORT`, `VERTICA_DATABASE`, `VERTICA_USER`, `VERTICA_PASSWORD`, and `VERTICA_SCHEMA` through the deployment secret manager; no credentials are stored here.
- Supabase/PostgreSQL storage: set `SUPABASE_DB_URL` only in the backend secret manager and set `ADJUSTMENT_PROJECT_KEY=limon_ldp_bmf`. Never expose this URL through a `VITE_` variable.

## Mock SSO and role-based access

The backend is authoritative for authorization. The React UI hides unavailable
actions, but every API endpoint independently checks the authenticated role.

| Capability | reader | functional_admin | technical_admin |
|---|:---:|:---:|:---:|
| Search, lineage, history | yes | yes | yes |
| Run previews | yes | yes | yes |
| Commit, cancel, proxy, batch, revert | no | yes | no |
| Health and retry reconciliation | no | no | yes |

Mock endpoints are available only with `AUTH_MODE=mock`:

- `GET /api/auth/mock-users`
- `POST /api/auth/mock-login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

The stable identity returned to the application contains `userId`, `email`,
`displayName`, `roles`, and derived permissions. Audit writes use this identity
instead of a local username. The production CACIB SSO adapter must return the
same identity shape and map enterprise groups to the internal roles. Mock login
must be disabled in production.

## Supabase adjustment storage

The reusable migration is [backend/migrations/001_supabase_adjustment_storage.sql](backend/migrations/001_supabase_adjustment_storage.sql). It creates:

- `out_completude_ldp_bmf`: immutable base, cancellation, and replacement output rows;
- `adjustment_projects`: reusable per-project field and calculation configuration;
- `adjustment_batches`: committed adjustment/revert transaction headers and idempotency;
- `adjustment_batch_items`: per-trade lineage and preview concurrency versions;
- `adjustment_field_changes`: typed before/after audit details;
- `adjustment_action_events`: append-only user activity and security audit events;
- `v_out_completude_ldp_bmf_current`: current effective row per source/context;
- `v_adjustment_register`: committed/reverted global register.

Database triggers reject updates and deletes from output and audit tables. Reverts are new append-only batches. Supabase RLS is enabled and `anon`/`authenticated` access is revoked because all access must pass through FastAPI.

## Real LiMon: Vertica output + PostgreSQL metadata

### Hybrid simulation in Supabase

Migration `004_hybrid_simulation.sql` creates two deliberately isolated schemas:

- `vertica_sim`: `output_completude_table` plus the technical idempotency link table;
- `adjustment_meta`: requests, committed batches, snapshots, field changes, and action events.

Run the web application against them with separate connection factories, even when both URLs point to the same Supabase project:

```env
STORAGE_MODE=hybrid_sim
ADJUSTMENT_PROJECT_KEY=limon_ldp_bmf
OUTPUT_DB_URL=postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require
METADATA_DB_URL=postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

The simulator never performs a cross-schema transaction or join from application code. Test crash recovery and duplicate prevention interactively with:

```bash
cd backend
../.venv/bin/python scripts/verify_hybrid_simulation.py
```

The hybrid workflow supports three append-only operations:

- `ADJUSTMENT`: one reversal and one adjusted replacement row.
- `TRADE_CANCELLATION`: one reversal row; the trade has no active business row afterward.
- `PROXY`: one new user-defined proxy row. The backend generates a stable trade
  number such as `PROXY-20260811-A1B2C3D4`, while the output adapter generates
  the physical `output_record_id`.

For an existing hybrid simulation database, apply
`backend/migrations/005_cancel_and_proxy_adjustments.sql` before using these
operations. The schema installer applies migrations in filename order.

### Mapping-assisted manual overrides

Mapping content is read directly from Parquet; it is not duplicated in
PostgreSQL. `backend/mapping_data/latest_mappings.json` maps each mapping name
to the latest immutable local or `s3://` Parquet path. Field names, output
columns, and downstream calculation stages are configured in
`backend/app/mapping_config.py`.

The initial controlled override fields are:

- `exposureClass`: skips `exposure_class`, then recalculates HQLA, reporting
  lines, and LCR impacts;
- `hqlaLevel`: skips `hqla`, then recalculates reporting lines and LCR impacts;
- `reportingLineLcr`: skips `reporting_lines`, then recalculates LCR impacts.

The adjustment UI loads distinct values from the configured Parquet output
column and provides a paginated mapping-table viewer. Preview and commit
validate the selected value again on the backend. Upstream fields are never
changed to fit the override. The resolved path, selected value, output column,
producer, and downstream stages are stored with the audit snapshot.

The repository includes three example Parquet files under
`backend/mapping_data/examples`. Regenerate and inspect them with:

```bash
cd backend
../.venv/bin/python scripts/generate_example_mappings.py
../.venv/bin/python scripts/read_mapping_parquet.py \
  mapping_data/examples/exposure_class_2026-08-12.parquet
```

Set `MAPPING_MANIFEST_PATH` to use another manifest. In production, replace the
local paths in that JSON with the versioned S3 paths supplied by LiMon. The
runtime uses the normal AWS credential chain when PyArrow reads `s3://` data.
Migration `006_mapping_audit_metadata.sql` adds only the JSON audit column; it
does not create a mapping schema or mapping tables.

The script injects a crash after the output commit, retries the same idempotency key, verifies exactly two generated output rows, and checks the net Power BI amount.

For local development without writing the database password to `.env` or shell history, start the API with:

```bash
cd backend
../.venv/bin/python scripts/run_hybrid_sim.py
```

Enter the password at the private prompt, then start the Vite frontend normally in a second terminal.
If the API uses a non-default port, point Vite to it without exposing any database secret:

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

### Production hybrid mode

Set `STORAGE_MODE=hybrid`. In this mode, the repository composition keeps `output_completude_table` and all physical cancellation/replacement rows in Vertica, while Supabase stores coordinator state, immutable audit snapshots, changes, idempotency, and user events. The API and adjustment service do not change.

Provide the existing enterprise connection factory as an import path:

```env
STORAGE_MODE=hybrid
LIMON_VERTICA_CONNECTION_FACTORY=limon.db:open_vertica_connection
VERTICA_OUTPUT_TABLE=output_completude_table
```

See [docs/hybrid-vertica-supabase.md](docs/hybrid-vertica-supabase.md) for the commit/recovery protocol and the exact production integration points. The hybrid coordinator tables are created by `003_hybrid_vertica_coordinator.sql`.

Apply the migration interactively without putting the password in shell history:

```bash
cd backend
.venv/bin/python scripts/apply_supabase_schema.py
```

Before production enablement, map domain fields to the reviewed schema, implement `get_effective_trade`, wire the existing LiMon Python functions, and review [the proposed audit DDL](docs/adjustment_audit.sql). The DDL is intentionally not applied automatically.

## Security model

The backend whitelist is the authorization boundary for editable fields.
Calculated fields are rejected even if a caller bypasses the UI. Authentication
is pluggable for the future CACIB SSO identity, while the internal application
roles remain `reader`, `functional_admin`, and `technical_admin`. Mock identities
exist only when `AUTH_MODE=mock`; authorization is always enforced by FastAPI,
not only by hidden frontend buttons.

## Developer onboarding guide

This section explains how the browser, API, calculation layer, Vertica output,
PostgreSQL metadata, Parquet mappings, and recovery process communicate. Read it
before changing an endpoint or adding an adjustment type.

### Source-code map

| Area | Responsibility | Start here |
|---|---|---|
| API composition | Creates dependencies, authorizes endpoints and translates domain errors to HTTP | `backend/app/main.py` |
| Request schemas | Validates HTTP request bodies and shared snapshot context | `backend/app/models.py` |
| Business workflow | Preview, commit, cancellation, proxy, batch and revert rules | `backend/app/services.py` |
| Calculation graph | Editable fields, additive measures and stage dependencies | `backend/app/config.py` |
| Mapping rules | Maps adjustable fields to Parquet outputs and downstream stages | `backend/app/mapping_config.py` |
| Mapping data | Resolves the latest Parquet path, searches rows and validates values | `backend/app/mappings.py` |
| Runtime selection | Selects Supabase, hybrid simulation or production hybrid repositories | `backend/app/storage.py` |
| Hybrid coordinator | Coordinates output writes and metadata without a distributed transaction | `backend/app/adapters/hybrid_adjustment_repository.py` |
| Simulated Vertica | Implements output behavior in the `vertica_sim` PostgreSQL schema | `backend/app/adapters/postgres_vertica_simulator.py` |
| Simulation audit | Stores requests, batches, snapshots and actions in `adjustment_meta` | `backend/app/adapters/postgres_simulation_audit_repository.py` |
| Real Vertica boundary | Minimal adapter for the production output database | `backend/app/adapters/vertica_repository.py` |
| Frontend orchestration | Queries, mutations, workspace state and dialogs | `frontend/src/App.tsx` |
| API client | The browser's typed REST boundary | `frontend/src/api.ts` |
| Shared UI types | API response and request shapes used by React | `frontend/src/types.ts` |
| Authentication UI | Mock login and session bootstrap | `frontend/src/AuthGate.tsx` |

### Communication levels

The application deliberately separates five communication levels:

1. **Browser state:** React owns temporary selections, drafts, previews and
   dialogs. Refreshing the page removes drafts but never committed data.
2. **HTTP API:** FastAPI authenticates the session, validates payloads and
   returns stable JSON shapes. The frontend never connects to a database.
3. **Domain service:** `AdjustmentService` applies business invariants and
   creates the rows that an operation would write.
4. **Repository boundary:** repositories hide whether output and metadata live
   in one PostgreSQL database, two simulated schemas, or Vertica + PostgreSQL.
5. **Physical storage:** output rows feed Power BI; metadata rows provide audit,
   idempotency, recovery and history.

```mermaid
flowchart LR
    User["User"] --> UI["React workspace"]
    UI -->|"JSON + session cookie"| API["FastAPI endpoints"]
    API --> Domain["AdjustmentService"]
    Domain --> Calc["LiMon calculation adapter"]
    Domain --> Map["Manifest + Parquet mappings"]
    Domain --> Repo["Repository interface"]
    Repo --> Output["Vertica output rows"]
    Repo --> Meta["PostgreSQL audit metadata"]
    Output --> BI["Power BI"]
```

### Snapshot selection and trade search

Every business read is scoped by the pair `asofdate` + `asofdateflow`. The date
identifies the reporting snapshot and the flow identifies its version. Never
query a trade using the date alone.

```mermaid
sequenceDiagram
    actor U as User
    participant UI as React
    participant API as FastAPI
    participant R as Output repository
    participant A as Audit repository

    U->>UI: Select as-of date
    UI->>API: GET /api/versions?asofdate=...
    API->>R: versions(asofdate)
    R-->>API: available flows
    API->>A: DATE_SELECTED event
    API-->>UI: flow list
    U->>UI: Select flow, Trade and FO system
    UI->>API: GET /api/trades?...search=...&foSystem=...
    API->>R: paginated lineage search
    R-->>API: original, reversal and replacement rows
    API-->>UI: only matching rows
    U->>UI: Open a row
    UI->>API: GET detail + lineage
    API->>R: read detail and complete lineage
    R-->>UI: active status and all associated rows
```

Search is mandatory because a LiMon snapshot can contain millions of rows. The
UI must not request or render an entire snapshot. A cancelled trade remains
readable for audit, but `get_effective_trade` rejects it for new writes because
it has no active business row.

### Standard adjustment preview and commit

Preview and commit intentionally call the same row-building rules. Preview is
read-only; commit re-reads the authoritative row and checks its version before
writing.

```mermaid
sequenceDiagram
    actor U as Functional administrator
    participant UI as React
    participant API as FastAPI
    participant S as AdjustmentService
    participant M as Parquet mappings
    participant C as Calculation adapter
    participant O as Vertica output
    participant P as PostgreSQL metadata

    U->>UI: Change authorized fields
    UI->>API: POST /api/adjustments/impact
    API-->>UI: impacted calculation stages
    U->>UI: Run preview
    UI->>API: POST /api/adjustments/preview
    API->>S: preview(context, rowId, changes)
    S->>O: read effective row
    S->>M: validate controlled values
    S->>S: build negative reversal
    S->>C: recalculate affected downstream stages
    C-->>S: adjusted row and calculated fields
    S-->>UI: original + reversal + replacement + rowVersion
    U->>UI: Apply adjustment with reason
    UI->>API: POST /api/adjustments/commit + idempotencyKey
    API->>S: commit(request, authenticated email)
    S->>O: re-read effective row
    S->>S: compare expectedVersion
    S->>P: reserve idempotent request
    S->>O: append reversal and replacement
    S->>P: store batch, snapshots, changes and mapping references
    API-->>UI: batch ID and COMMITTED status
    UI->>API: refresh detail, lineage and history
```

Example preview request:

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001",
  "changes": {
    "amount": 1250000,
    "exposureClass": "SOVEREIGN"
  }
}
```

Example commit adds concurrency and retry protection:

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001",
  "changes": {
    "amount": 1250000,
    "exposureClass": "SOVEREIGN"
  },
  "reason": "Correct exposure classification after source review",
  "expectedVersion": "<hash returned by preview>",
  "idempotencyKey": "<one UUID reused for retries>"
}
```

### Why reversal and replacement rows are written

The output table is append-only because it feeds Power BI and must remain
auditable. For every additive measure `x`:

```text
BASE.x + ADJUSTMENT_CANCEL.x = BASE.x + (-BASE.x) = 0
0 + ADJUSTMENT_REPLACEMENT.x = corrected business value
```

Power BI can therefore aggregate all record types and obtain the corrected
total. Users who want only unadjusted source rows can filter `record_type =
'BASE'`. Never update or delete an output row to implement a business action.

### Mapping-assisted selection

`mapping_config.py` answers *which mapping and calculation stages belong to a
field*. `latest_mappings.json` answers *where the latest Parquet is*. The
Parquet file answers *which values and mapping rows exist*.

```mermaid
sequenceDiagram
    participant UI as Mapping selector
    participant API as Mapping endpoints
    participant CFG as mapping_config.py
    participant J as latest_mappings.json
    participant PQ as Parquet local/S3

    UI->>API: GET /api/mappings/fields
    API->>CFG: controlled field definitions
    API->>J: resolve mapping name
    API-->>UI: labels, columns and resolved source
    UI->>API: GET /api/mappings/values?field=exposureClass
    API->>PQ: read output column
    PQ-->>API: mapping rows
    API-->>UI: sorted distinct values
    UI->>API: GET /api/mappings/{name}/rows?page=1
    API-->>UI: searchable paginated rows
```

When adding a controlled field:

1. Add it to `EDITABLE_FIELDS`.
2. Add one entry to `MAPPING_FIELDS` with its mapping name, output column,
   producer stage and downstream stages.
3. Add the mapping name and immutable Parquet path to the JSON manifest.
4. Add provider and service tests.
5. Confirm the exact resolved path appears in committed audit metadata.

### Direct cancellation

Cancellation is a commit operation, not a destructive delete and not a normal
modification preview. The UI silently obtains the current row version, asks for
a reason, and commits one negative reversal row.

```text
BASE (active) → ADJUSTMENT_CANCEL (negative) → no active business row
```

The cancelled trade remains searchable and its lineage remains visible. A new
adjustment is forbidden until the cancellation is reverted.

### Proxy trade

A proxy creates a new business row without an original or reversal. The user
provides business characteristics; the backend generates the trade number and
the output adapter generates the physical record ID.

```text
User fields + context + draft ID
              ↓
        preview calculation
              ↓
PROXY-YYYYMMDD-XXXXXXXX + output_record_id
              ↓
       one append-only PROXY row
```

The draft ID makes preview output stable, while the idempotency key prevents a
double commit if the browser retries.

### Batch adjustment

A batch contains multiple standard adjustments for the same snapshot context.
Each item retains its own preview version. The batch preview aggregates changed
trades, output row count, stages and numeric deltas. Commit fails if any item is
stale; it must never partially accept a business batch.

### Revert workflow

Revert is another append-only adjustment linked to the batch being undone. It
does not delete the original commit. The register pairs the original commit and
its revert so users can distinguish `COMMITTED` from `REVERTED` actions.

```mermaid
sequenceDiagram
    actor U as Functional administrator
    participant UI as History/Register
    participant API as FastAPI
    participant S as AdjustmentService
    participant O as Output
    participant P as Metadata

    U->>UI: Revert adjustment + reason
    UI->>API: POST /api/adjustments/{batch}/revert
    API->>S: validate target and current lineage
    S->>O: append rows restoring prior business effect
    S->>P: create REVERT batch linked to original batch
    API-->>UI: new audit batch ID
    UI->>API: refresh register and lineage
```

### Hybrid commit, failure and reconciliation

Vertica and PostgreSQL cannot share one ACID transaction. The hybrid repository
therefore uses a recoverable coordinator protocol:

1. Reserve the idempotency key in PostgreSQL.
2. Build and store the intended immutable snapshot.
3. Commit output rows in Vertica, including `adjustment_reference`.
4. Finalize PostgreSQL metadata as `COMMITTED`.
5. If step 4 fails after Vertica commits, mark the request
   `RECONCILIATION_REQUIRED`.

`RECONCILIATION_REQUIRED` means the business output already exists, but its
metadata finalization is incomplete. Retrying reconciliation searches Vertica
by the stable adjustment reference and completes metadata without inserting
duplicate output rows. A business revert is enabled only after reconciliation
has reconstructed a complete committed batch.

### Idempotency, optimistic concurrency and errors

- **Idempotency key:** one UUID per user commit intention. Reuse it when a
  request is retried after a timeout; generate a new one after the user changes
  the draft.
- **Row version:** SHA-256 of stable effective-row content. Commit returns HTTP
  `409` when the row changed after preview.
- **Domain error:** invalid value, forbidden field or inactive trade; returned
  as `422`.
- **Conflict:** stale version or incompatible current state; returned as `409`.
- **Infrastructure error:** storage or coordination failure; returned as `503`.
- **Authentication/authorization:** missing session or permission; returned as
  `401` or `403`.

The frontend catches every failed mutation and displays the backend `detail`
message in the application notice. It must not report success until the API
returns a successful commit response.

### Backend extension checklist

For a new adjustment type:

1. Add a Pydantic request model.
2. Add preview/commit methods in `AdjustmentService`.
3. Keep output construction deterministic and append-only.
4. Add repository methods only when existing generic commit methods cannot
   represent the operation.
5. Add an authenticated endpoint with the narrowest permission.
6. Persist action type, snapshots, user, reason and idempotency reference.
7. Add domain tests, authorization tests and failure/retry tests.
8. Add typed frontend API methods and response types.
9. Invalidate the affected React Query caches after success.

### Frontend state and cache rules

- React component state holds drafts and open dialogs.
- React Query owns server state such as dates, trades, lineage and history.
- Query keys include every server-side scope value (`asofdate`, flow, row ID,
  filters and page).
- A successful write calls `invalidateQueries()` so active views re-read the
  authoritative backend state.
- `singleCommitKey`, `batchCommitKey` and `revertCommitKey` are refs because a
  rerender must not create a new retry identity.
- Changing a draft clears its prior preview and idempotency key.

### Tests expected before a pull request

```bash
cd backend
../.venv/bin/pytest -q

cd ../frontend
npm run build
```

For storage or reconciliation changes, also run the hybrid verification script
against the simulation schemas. Never run integration verification against a
production Vertica table.
