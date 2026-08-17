# Changes from `main` to `feature/dataframe-enrichment-pipeline`

This document compares `origin/main` at commit `4805609` with
`feature/dataframe-enrichment-pipeline` at commit `aecc928`.

## Summary

- 13 feature commits after `main`.
- 86 files changed before this document was added.
- 8,925 lines added and 1,827 lines removed.
- Adjustment, cancellation, proxy, batch, mapping, SSO, AG Grid and DataFrame
  enrichment workflows were added.
- Storage was reduced to one architecture using `vertica_sim` for output and
  `adjustment_meta` for metadata.

Local `.idea` files and untracked user guides are not part of the branch.

## Root configuration and documentation

| File | Status | Change |
|---|---|---|
| `.env.example` | Modified | Replaces multiple storage-mode variables with one `DATABASE_URL`; documents the project key, mapping manifest, failure injection, mock SSO and API port 8001. |
| `README.md` | Expanded | Adds architecture, setup, authentication, workflows, mappings, batch selection, reconciliation, DataFrame calculations, the semantic dictionary, testing and developer onboarding. Removes obsolete storage modes. |
| `docs/api-testing-guide.md` | Added | Documents the API routes with Swagger and curl examples, permissions, request bodies and expected workflows. |
| `docs/hybrid-vertica-supabase.md` | Deleted | Removes documentation for the unsupported production hybrid mode. |

## Backend application

### Authentication and API

| File | Status | Change |
|---|---|---|
| `backend/app/auth.py` | Added | Implements mock SSO identities, signed HTTP-only sessions, login/logout, role-to-permission mapping and FastAPI authorization dependencies. |
| `backend/app/main.py` | Modified | Adds authentication, FO-system lookup, batch filtering, mapping routes, cancellation, proxy, batch preview/commit, history, register, revert and reconciliation. It also provides structured configuration and database errors. |
| `backend/app/models.py` | Modified | Adds typed request models and Swagger examples for batch search, cancellation, proxy, batch commit and revert. |
| `backend/app/domain/repositories.py` | Modified | Extends repository contracts with FO-system selection, batch search and reconciliation lookup. |

### Central field and mapping configuration

| File | Status | Change |
|---|---|---|
| `backend/app/config.py` | Modified | Derives editable/additive fields from the data dictionary, expands the calculation graph and defines safe batch filters. |
| `backend/app/data_dictionary.py` | Added | Loads and validates the semantic field catalog and resolves API, database, Parquet and frontend representations. |
| `backend/config/data_dictionary.yaml` | Added | Canonical source for semantic IDs, labels, types, API names, database columns, Parquet columns and calculation behavior. |
| `backend/app/mapping_config.py` | Added | Configures controlled exposure class, HQLA and reporting-line overrides and their downstream stages. |
| `backend/app/mappings.py` | Added | Resolves the mapping manifest, reads/caches Parquet, searches mapping rows and validates manual selections. |

### Business workflows

| File | Status | Change |
|---|---|---|
| `backend/app/services.py` | Modified | Adds cancellation, proxy, multi-trade batches, manual mapping overrides, prerequisite expansion and calculation execution metadata. It preserves reversals, optimistic locking and idempotency. |
| `backend/app/repository.py` | Modified | Expands the test fixture with realistic trades, FO-system selection, structured filtering and lineage behavior. |

## DataFrame enrichment library

| File | Status | Change |
|---|---|---|
| `backend/lib/__init__.py` | Added | Declares the LiMon calculation library package. |
| `backend/lib/enrichments/__init__.py` | Added | Exposes the DataFrame calculation adapter. |
| `backend/lib/enrichments/contracts.py` | Added | Defines calculation context, registry definitions, validation errors and execution metadata. |
| `backend/lib/enrichments/pipeline.py` | Added | Runs registered functions on pandas DataFrames, injects Parquet parameters and validates result cardinality. |
| `backend/lib/enrichments/registry.py` | Added | Explicitly registers every calculation stage, function, input, output and mapping dependency. |
| `backend/lib/enrichments/rules.py` | Added | Implements the parameter-free maturity and EUR bucket rule. |
| `backend/lib/enrichments/parameter.py` | Added | Implements exact/wildcard parameter matching plus instrument, issuer, counterparty, FX, exposure, HQLA, reporting-line and LCR enrichments. |

## Storage architecture

The branch supports only this composition:

```text
DATABASE_URL
├── vertica_sim
│   ├── output_completude_table
│   └── output_adjustment_links
└── adjustment_meta
    ├── projects
    ├── requests
    ├── batches
    ├── item_snapshots
    ├── field_changes
    └── action_events
```

### Retained storage files

| File | Status | Change |
|---|---|---|
| `backend/app/storage.py` | Rewritten | Removes storage-mode selection and always builds the two-schema repositories using `DATABASE_URL`. |
| `backend/app/adapters/postgres_vertica_simulator.py` | Added | Implements snapshot reads, search, lineage and append-only output insertion in `vertica_sim`. |
| `backend/app/adapters/postgres_simulation_audit_repository.py` | Added | Implements request reservation, batches, snapshots, events, history, revert eligibility and recovery in `adjustment_meta`. |
| `backend/app/adapters/simulation_adjustment_repository.py` | Added | Coordinates output and metadata commits, idempotent retry, simulated failures and reconciliation. |

### Removed storage files

| File | Status | Reason |
|---|---|---|
| `backend/app/adapters/postgres_adjustment_repository.py` | Deleted | Removes monolithic Supabase storage. |
| `backend/app/adapters/postgres_audit_repository.py` | Deleted | Removes the incomplete production audit adapter. |
| `backend/app/adapters/vertica_repository.py` | Deleted | Removes the production Vertica boundary. |
| `backend/app/adapters/hybrid_adjustment_repository.py` | Replaced | Renamed and specialized as `simulation_adjustment_repository.py`. |
| `backend/app/adapters/limon_calculation_adapter.py` | Deleted | Removes the obsolete calculation placeholder. |

## Database migrations

| File | Status | Change |
|---|---|---|
| `backend/migrations/001_simulation_storage.sql` | Added | Creates both schemas, append-only protection, output tables, metadata tables, indexes, constraints and initial rows. |
| `backend/migrations/002_cancel_and_proxy_adjustments.sql` | Added | Adds cancellation/proxy operation types and supports variable output-row counts. |
| `backend/migrations/003_mapping_audit_metadata.sql` | Added | Adds mapping override audit metadata and removes the obsolete mapping schema. |
| `backend/migrations/004_seed_batch_selection_examples.sql` | Added | Adds realistic rows for FO-system batch filtering. |
| `backend/migrations/005_repair_batch_example_trade_prefixes.sql` | Added | Corrects Murex and Orchestrade example trade prefixes. |
| `backend/migrations/001_supabase_adjustment_storage.sql` | Deleted | Removes public-schema monolithic storage. |
| `backend/migrations/002_seed_output_examples.sql` | Deleted | Removes public-schema examples. |
| `backend/migrations/003_hybrid_vertica_coordinator.sql` | Deleted | Removes the production hybrid coordinator schema. |

## Mapping data

| File | Status | Purpose |
|---|---|---|
| `backend/mapping_data/latest_mappings.json` | Added | Maps logical mapping names to current Parquet versions. |
| `examples/counterparty_2026-08-13.parquet` | Added | Counterparty classification data. |
| `examples/exposure_class_2026-08-12.parquet` | Added | Previous exposure-class example version. |
| `examples/exposure_class_2026-08-13.parquet` | Added | Current exposure-class parameters. |
| `examples/fx_rate_2026-08-13.parquet` | Added | Currency-to-EUR rates. |
| `examples/hqla_2026-08-12.parquet` | Added | Previous HQLA example version. |
| `examples/hqla_2026-08-13.parquet` | Added | Current HQLA parameters. |
| `examples/instrument_classification_2026-08-13.parquet` | Added | Raw instrument classification data. |
| `examples/issuer_2026-08-13.parquet` | Added | Issuer country and rating data. |
| `examples/lcr_factor_2026-08-13.parquet` | Added | LCR inflow/outflow factors. |
| `examples/reporting_line_2026-08-12.parquet` | Added | Previous reporting-line example version. |
| `examples/reporting_line_2026-08-13.parquet` | Added | Current reporting-line parameters. |

All paths above are under `backend/mapping_data/`.

## Backend scripts

| File | Status | Change |
|---|---|---|
| `backend/scripts/apply_simulation_schema.py` | Added | Applies retained migrations and reports schema row counts. |
| `backend/scripts/run_simulation.py` | Added | Loads `.env`, requires `DATABASE_URL` and starts the API. |
| `backend/scripts/verify_simulation.py` | Added | Tests failure recovery, idempotency, output rows and net bucket amounts. |
| `backend/scripts/build_example_parameters.py` | Added | Builds the current example Parquet catalog. |
| `backend/scripts/generate_example_mappings.py` | Added | Builds initial mapping examples. |
| `backend/scripts/read_mapping_parquet.py` | Added | Displays a Parquet schema and rows for inspection. |
| `backend/scripts/generate_frontend_fields.py` | Added | Generates TypeScript field metadata from the YAML dictionary. |
| `backend/scripts/apply_supabase_schema.py` | Deleted | Replaced by the simulation schema installer. |
| `backend/scripts/inspect_supabase_adjustments.py` | Deleted | Removes monolithic storage inspection. |
| `backend/scripts/verify_supabase_runtime.py` | Deleted | Removes monolithic storage verification. |

## Dependencies

| File | Status | Change |
|---|---|---|
| `backend/requirements.txt` | Modified | Adds PyArrow, pandas and PyYAML. |
| `frontend/package.json` | Modified | Adds AG Grid Community and removes TanStack Table. |
| `frontend/package-lock.json` | Modified | Locks the updated frontend dependency graph. |

## Backend tests

| File | Status | Coverage |
|---|---|---|
| `backend/tests/test_adjustments.py` | Expanded | Reversal/replacement, calculation union, buckets, cancellation, proxy, mappings, concurrency, idempotency and multi-trade batches. |
| `backend/tests/test_api_routes.py` | Added | Authenticated routes and structured configuration/database errors. |
| `backend/tests/test_auth.py` | Added | Login, sessions, roles, permissions and denied access. |
| `backend/tests/test_data_dictionary.py` | Added | Labels, editability, additive fields, dependencies and duplicate validation. |
| `backend/tests/test_enrichment_pipeline.py` | Added | Buckets, wildcard priority, ambiguity, execution metadata and registry completeness. |
| `backend/tests/test_mappings.py` | Added | Manifest resolution, values, search, pagination and override validation. |
| `backend/tests/test_simulation_reconciliation.py` | Added | Recovery from existing output rows and incomplete-batch rejection. |
| `backend/tests/test_storage.py` | Added | Verifies the single two-schema composition and mandatory `DATABASE_URL`. |
| `backend/tests/test_hybrid_reconciliation.py` | Replaced | Renamed to the simulation-specific reconciliation tests. |

At the time of writing, 41 backend tests pass.

## Frontend startup and authentication

| File | Status | Change |
|---|---|---|
| `frontend/.env.example` | Added | Points the Vite API proxy to port 8001. |
| `frontend/vite.config.ts` | Modified | Loads environment variables and proxies `/api`. |
| `frontend/src/main.tsx` | Modified | Adds the authentication gate around the application. |
| `frontend/src/AuthGate.tsx` | Added | Implements development identity selection, session bootstrap, logout and denied-access handling. |
| `frontend/src/auth.css` | Added | Styles login identities, authenticated avatar and user popover. |

## Frontend application and API

| File | Status | Change |
|---|---|---|
| `frontend/src/App.tsx` | Heavily modified | Adds separate Workspace/Register navigation, date picker, version combobox, clearable search, closable trade tabs, AG Grid lineage, cancellation, proxy, mapping popovers, batch selection, impact preview, commit, revert and reconciliation. |
| `frontend/src/api.ts` | Modified | Adds typed calls for auth, FO systems, batch filtering, mappings, cancellation, proxy, history, register, revert and reconciliation. |
| `frontend/src/types.ts` | Modified | Adds lineage, proxy, cancellation, batch, mapping, history, role and identity types. |
| `frontend/src/generated/fields.ts` | Added | Contains generated frontend field labels, semantic IDs, types and editable/additive flags. |

## Frontend styling

| File | Status | Change |
|---|---|---|
| `frontend/src/styles.css` | Expanded | Adds the CACIB white/green design, minimalist panels, dialogs, forms, tabs, previews and responsive layout. |
| `frontend/src/batch.css` | Added | Styles AG Grid batch selection, filters, editors and impact preview. |
| `frontend/src/mapping.css` | Added | Styles mapping value popovers, scrolling and mapping-table views. |
| `frontend/src/revert.css` | Modified | Makes revert actions red and visually links commits to their reverts. |
| `frontend/src/search-lineage.css` | Modified | Adds compact lineage/status tags and active/cancelled row highlighting. |

## Feature progression

The current branch combines the following successive feature sets:

1. Two-schema simulation storage with recoverable commits.
2. Trade cancellation and proxy creation.
3. Mock SSO and role-based authorization.
4. Parquet-based mapping assistance.
5. Cancelled-trade visibility and mapping UI refinement.
6. API and communication documentation.
7. AG Grid search and FO-system batch selection.
8. DataFrame enrichment functions.
9. Central semantic field dictionary.
10. Removal of every storage mode except `vertica_sim` + `adjustment_meta`.
