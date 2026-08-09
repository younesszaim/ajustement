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

The running application uses Supabase/PostgreSQL storage exclusively. The in-memory repository is retained only as an isolated automated-test fixture and is never selected by FastAPI. Business calculations still live behind `MockCalculationAdapter` until the production LiMon functions are connected through `backend/app/adapters/limon_calculation_adapter.py`.

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
- Local identity: `LOCAL_USER` (defaults to `developer@example`)
- Runtime storage: `SUPABASE_DB_URL` must be set as a backend secret. FastAPI has no mock-storage runtime switch.
- Vertica: provide `VERTICA_HOST`, `VERTICA_PORT`, `VERTICA_DATABASE`, `VERTICA_USER`, `VERTICA_PASSWORD`, and `VERTICA_SCHEMA` through the deployment secret manager; no credentials are stored here.
- Supabase/PostgreSQL storage: set `SUPABASE_DB_URL` only in the backend secret manager and set `ADJUSTMENT_PROJECT_KEY=limon_ldp_bmf`. Never expose this URL through a `VITE_` variable.

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
