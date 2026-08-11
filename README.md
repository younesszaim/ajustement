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

Migration `006_mapping_simulation.sql` creates `mapping_sim`, a Supabase mock
of the production mapping registry and latest Parquet content. The registry
maps a LiMon field to a mapping name, latest S3 path, output column, producer
stage, and downstream calculation stages.

The initial controlled override fields are:

- `exposureClass`: skips `exposure_class`, then recalculates HQLA, reporting
  lines, and LCR impacts;
- `hqlaLevel`: skips `hqla`, then recalculates reporting lines and LCR impacts;
- `reportingLineLcr`: skips `reporting_lines`, then recalculates LCR impacts.

The adjustment UI loads distinct values from the latest mapping output column
and provides a paginated mapping-table viewer. Preview and commit validate the
selected value again on the backend. Upstream fields are never changed to fit
the override. The selected mapping name, S3 source, output column, producer,
and downstream stages are stored with the audit snapshot.

Set `MAPPING_DB_URL` for a separate mapping connection. In hybrid simulation it
falls back to `METADATA_DB_URL`; in Supabase-only mode it falls back to
`SUPABASE_DB_URL`. The future S3 Parquet provider must implement the same
`fields`, `values`, `rows`, and `validate_overrides` contract.

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

The backend whitelist is the authorization boundary for editable fields. Calculated fields are rejected even if a caller bypasses the UI. Authentication is pluggable for SSO/reverse-proxy identity; the MVP assumes `VIEWER`, `ADJUSTER`, and `ADMIN` roles and exposes local development as an adjuster.
