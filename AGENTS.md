# LiMon Adjustment Manager — agent guide

This file is the entry point for any human or AI contributor. Read it before
editing. More specific `AGENTS.md` files apply inside `streamlit_app/`,
`streamlit_app/tests/`, `streamlit_app/migrations/`, `backend/`, `frontend/`,
`backend/migrations/`, and `backend/lib/enrichments/`.

## Choose the correct application first

This repository temporarily contains two implementations:

- `streamlit_app/` is the active simplified prototype: Streamlit UI, small
  FastAPI API, one output table, and one PostgreSQL operation table.
- `backend/` plus `frontend/` is the older React/FastAPI implementation. Keep
  it as reference unless the request explicitly names the React application.

For requests phrased as “the application”, “Streamlit”, “the simple API”, or
the latest workflow, work in `streamlit_app/`. Do not make matching edits in
the legacy implementation for consistency. If the requested target is truly
ambiguous and the choice would materially change the result, inspect recent
documentation and ask before editing both applications.

## Mission

LiMon lets users preview and append audited corrections to version-scoped
trade output. The application never updates or deletes production facts.

## Start here

1. Identify the active application using the section above.
2. For Streamlit work, read `streamlit_app/AGENTS.md` and
   `docs/streamlit-fastapi-architecture.md`.
3. For legacy React work, read `docs/ai-agent-guide.md` and the scoped backend
   or frontend guide.
4. Follow `docs/change-workflow.md` for a feature or bug fix.
5. Use copy-ready task prompts from `docs/ai-prompts.md` when helpful.
6. Read the nearest scoped `AGENTS.md` before modifying a file.
7. Read applicable accepted decisions in `docs/adr/`.
8. Use the active application's YAML configuration for business field names.
9. Run the checks documented by the nearest scoped guide before handoff.

## Non-negotiable invariants

- Every trade read and write is scoped by the complete configured snapshot.
- Output is append-only. Never update or physically delete an output row.
- A standard adjustment appends a negative reversal and one replacement.
- A revert is a new audited operation, not deletion of history.
- Preview and commit must use the same row-building and calculation logic.
- Commit re-reads the active row and rejects incompatible current state.
- Retry of one commit intention reuses one idempotency key.
- Output and audit storage communicate through repository contracts. Do not
  make UI code or domain services issue SQL.
- No browser UI connects directly to PostgreSQL, Vertica, Parquet, or S3.
- Do not hard-code aliases for business fields. Use the field catalog belonging
  to the selected implementation.
- There is currently no application authentication or authorization layer.
  Audit actions use the configured `AUDIT_ACTOR`.
- Never mix the Streamlit semantic field catalog with the legacy generated
  React catalog. They have separate configuration and contracts.

## Repository map

| Path | Responsibility |
|---|---|
| `streamlit_app/app.py` | Active Streamlit UI and browser-session state |
| `streamlit_app/client.py` | Streamlit-to-FastAPI HTTP boundary |
| `streamlit_app/api.py` | Simple API routes and HTTP error translation |
| `streamlit_app/service.py` | Simple preview, commit, retry and revert rules |
| `streamlit_app/storage.py` | Output and one-table metadata SQL boundaries |
| `streamlit_app/calculations.py` | Ordered DataFrame recalculation pipeline |
| `streamlit_app/project*.yaml` | Semantic-to-physical field configuration |
| `backend/app/main.py` | FastAPI composition and HTTP error translation |
| `backend/app/models.py` | Request contracts and Swagger examples |
| `backend/app/services.py` | Adjustment domain workflows and invariants |
| `backend/app/domain/` | Repository interfaces and domain contracts |
| `backend/app/adapters/` | PostgreSQL storage implementations/coordinator |
| `backend/lib/enrichments/` | DataFrame calculation functions and registry |
| `backend/config/data_dictionary.yaml` | Canonical field catalog |
| `backend/mapping_data/` | Latest mapping manifest and example Parquet |
| `frontend/src/api.ts` | Typed browser-to-API boundary |
| `frontend/src/types.ts` | Shared frontend API shapes |
| `frontend/src/App.tsx` | Workspace orchestration and server-state queries |
| `backend/tests/` | Executable business and infrastructure contracts |

## Safe workflow

- Inspect before editing; preserve unrelated and untracked user files.
- Prefer a focused domain change with tests over cross-layer duplication.
- For an API change, update model, route, typed client, UI, examples, and tests.
- For a field change, follow `docs/feature-playbooks.md`; never globally replace
  a physical column name without checking API, DB, Parquet, and label mappings.
- For a bug, reproduce it and add a regression guard before changing behavior
  when practical. Trace the cause across layers instead of patching the symptom.
- For a feature, define output journal, effective state, failure behavior,
  idempotency, audit metadata, and UI refresh behavior before implementation.
- Record a decision in `docs/adr/` when changing an accepted invariant or a
  cross-cutting architecture boundary.
- Migrations are forward-only. Never rewrite an applied migration.
- Do not commit secrets, `.env`, database URLs, build output, or IDE files.

## Commands

```bash
make check
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests -q
make test-backend
make test-frontend
make build-frontend
make generate-fields
```

Database integration scripts require `DATABASE_URL` and are intentionally not
part of the default check. See `README.md` before running them.

## Definition of done

- The requested behavior is implemented at the correct layer.
- Relevant happy-path, failure, retry, and invariant tests exist.
- Swagger examples and typed frontend contracts agree with the backend.
- Generated field metadata is current.
- `make check` succeeds.
- Documentation is updated when an invariant, endpoint, environment variable,
  or contributor workflow changes.
- The final handoff lists behavior, tests, migrations/configuration, limitations,
  and whether the working tree was committed.
