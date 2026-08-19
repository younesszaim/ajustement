# Changes from `main` to `feature/configured-field-options`

This document describes the cumulative application state on
`feature/configured-field-options`, including the current working-tree changes,
relative to `main`. It is intended as a technical handoff, not a commit log.

Untracked IDE files, generated user guides and screenshots are not application
changes and are intentionally excluded.

## Executive summary

The branch transforms the initial adjustment prototype into an append-only,
version-scoped LiMon application with:

- output simulation in `vertica_sim` and audit metadata in `adjustment_meta`;
- standard adjustment, cancellation, proxy, batch, revert and reconciliation;
- AG Grid trade search, lineage and server-filtered batch selection;
- DataFrame enrichment functions and a central semantic field dictionary;
- project-configured dropdown values instead of user-facing mapping tables;
- immutable Cash/Titre leg filtering and adjustment of the applicable EUR amount;
- bucket, LCR and LDP-impact recalculation;
- AI/developer operating guides and executable API examples;
- no application authentication or authorization layer.

At the time of this update, `make check` passes with 45 backend tests and a
successful TypeScript/Vite production build. Vite still reports the existing
large-bundle advisory warning.

## Architecture retained by the branch

```text
React + AG Grid
    ↓ typed HTTP API
FastAPI routes
    ↓
AdjustmentService + DataFrame enrichment pipeline
    ↓
SimulationAdjustmentRepository
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

Only `DATABASE_URL` is used by the retained storage composition. The output and
metadata repositories remain logically isolated even when they share one
PostgreSQL/Supabase instance.

## Business invariants added

- Every read and write is scoped by `asofdate` and `asofdateflow`.
- Output facts are append-only; adjustment and revert never physically delete.
- A standard adjustment writes a negative reversal and a replacement.
- A cancellation writes one reversal and leaves no active row.
- A proxy writes one backend-identified trade.
- Preview and commit share the same row builder and calculations.
- Commit checks `rowVersion` and uses a stable idempotency key.
- Reconciliation repairs metadata after a partial output/audit failure without
  duplicating output rows.
- `security_leg_flag` is immutable context: `0 = Cash`, `1 = Titre`.
- The leg filters trade selection and is never accepted in adjustment `changes`.
- Only `cashAmountEur` is adjustable for Cash rows; only
  `securityAmountEur` is adjustable for Titre rows.

## Root configuration and contributor support

| File | Status | Current change |
|---|---|---|
| `.env.example` | Modified | Documents the single database URL, project key, mapping manifest, failure injection, audit actor and API port. |
| `Makefile` | Added | Provides tests, frontend build and semantic-field generation/check commands. |
| `AGENTS.md` | Added | Defines repository-wide architecture, safety and completion rules for AI/human contributors. |
| `CLAUDE.md` | Added | Routes Claude contributors to the same repository guidance. |
| `README.md` | Expanded | Documents setup, storage, workflows, calculations, controlled options, Cash/Titre behavior, rollback guidance and developer onboarding. |
| `docs/ai-agent-guide.md` | Added | Explains boundaries and end-to-end communication flows. |
| `docs/ai-prompts.md` | Added | Supplies reusable prompts for features, fixes, reviews and documentation. |
| `docs/change-workflow.md` | Added | Defines the operational feature/bug workflow. |
| `docs/feature-playbooks.md` | Added | Provides focused implementation playbooks. |
| `docs/testing-strategy.md` | Added | Describes unit, integration and manual verification expectations. |
| `docs/adding-fields-guide.md` | Added | Step-by-step guide for adding displayed, searchable, filtered or adjustable fields. |
| `docs/api-testing-guide.md` | Added/updated | Documents Swagger/curl flows, configured options and Cash/Titre adjustment examples. |
| `docs/hybrid-vertica-supabase.md` | Deleted | Removes the unsupported older hybrid-mode documentation. |

## Backend API and domain

| File | Status | Current change |
|---|---|---|
| `backend/app/main.py` | Modified | Adds snapshot/trade routes, FO systems, leg-aware search, batch filtering, adjustment options, preview/commit, cancellation, proxy, history, revert and reconciliation with structured errors. Public mapping-table routes were removed. |
| `backend/app/models.py` | Modified | Adds realistic typed request contracts and Swagger examples for all mutation workflows. |
| `backend/app/services.py` | Expanded | Implements shared preview/commit row building, additive reversal, cancellation, proxy, batch, optimistic concurrency, controlled-value validation, Cash/Titre amount validation and calculation execution metadata. |
| `backend/app/domain/repositories.py` | Expanded | Defines output/audit contracts including leg-aware search, batch selection and reconciliation. |
| `backend/app/repository.py` | Expanded | Provides realistic in-memory examples, Cash/Titre fixtures, lineage and scoped filters for tests. |
| `backend/app/config.py` | Modified | Derives editable/additive fields, defines calculation dependencies and safe batch filters including `securityLegFlag`. |
| `backend/app/project_config.py` | Added | Central source for small reviewed dropdown options such as exposure class, HQLA and LCR reporting line. |
| `backend/app/mapping_config.py` | Deleted | Removes the old UI-facing mapping-field catalog. |
| `backend/app/mappings.py` | Simplified | Retains manifest/Parquet loading only for internal calculation parameter tables; value search and table browsing were removed. |

## Semantic field dictionary

| File | Status | Current change |
|---|---|---|
| `backend/app/data_dictionary.py` | Added | Loads and validates semantic IDs, API names, physical DB columns, parameter columns, labels, types and calculation metadata. |
| `backend/config/data_dictionary.yaml` | Added/expanded | Defines the canonical field catalog, including immutable leg, Cash/Security amounts and six additive LDP-impact outputs. |
| `frontend/src/generated/fields.ts` | Generated | Exposes labels, semantic IDs, types and editable/additive flags to React. |
| `backend/scripts/generate_frontend_fields.py` | Added | Regenerates frontend metadata from YAML. |

The `parquet` property remains only for columns read from internal parameter
tables. It is unrelated to the removed mapping viewer.

## DataFrame enrichment pipeline

| File | Status | Current change |
|---|---|---|
| `backend/lib/enrichments/contracts.py` | Added | Defines enrichment definitions, validation errors, context and execution metadata. |
| `backend/lib/enrichments/pipeline.py` | Added | Executes registered DataFrame functions, injects parameter tables and preserves row cardinality. |
| `backend/lib/enrichments/registry.py` | Added/expanded | Registers instrument, issuer, counterparty, FX, leg amount, buckets, exposure, HQLA, reporting line, LCR and LDP stages. |
| `backend/lib/enrichments/parameter.py` | Added | Implements exact/wildcard parameter matching and parameter-driven enrichment functions. |
| `backend/lib/enrichments/rules.py` | Added/expanded | Implements maturity buckets, immutable-leg amount selection and deterministic LDP-impact calculations. |
| `backend/mapping_data/latest_mappings.json` | Added | Resolves logical parameter names to current example Parquet files. |
| `backend/mapping_data/examples/*.parquet` | Added | Supplies local examples for classification, FX, exposure, HQLA, reporting-line and LCR calculations. |

The current LDP formulas are explicit simulator rules and are isolated so real
LiMon functions can replace them without moving calculations into React.

## Storage adapters

| File | Status | Current change |
|---|---|---|
| `backend/app/storage.py` | Rewritten | Always builds the retained two-schema simulation composition. |
| `backend/app/adapters/postgres_vertica_simulator.py` | Added/expanded | Implements snapshot reads, leg-aware search, lineage, batch filtering, semantic row mapping and append-only insertion of Cash/Security/LDP values. |
| `backend/app/adapters/postgres_simulation_audit_repository.py` | Added/updated | Stores requests, batches, snapshots, field changes, actions and controlled-selection metadata. |
| `backend/app/adapters/simulation_adjustment_repository.py` | Added | Coordinates output and metadata writes, idempotency, failure injection and reconciliation. |

Removed obsolete adapters:

- `postgres_adjustment_repository.py`;
- `postgres_audit_repository.py`;
- `vertica_repository.py`;
- `hybrid_adjustment_repository.py`;
- `limon_calculation_adapter.py`.

## Database migrations

| Migration | Current change |
|---|---|
| `001_simulation_storage.sql` | Creates `vertica_sim`, `adjustment_meta`, append-only tables, constraints, indexes and initial output rows. |
| `002_cancel_and_proxy_adjustments.sql` | Adds cancellation/proxy action types and variable output counts. |
| `003_mapping_audit_metadata.sql` | Retains the JSON audit column used for controlled-selection metadata and removes obsolete mapping storage. |
| `004_seed_batch_selection_examples.sql` | Adds realistic FO-system examples for AG Grid batch filtering. |
| `005_repair_batch_example_trade_prefixes.sql` | Corrects development fixture prefixes. |
| `006_add_leg_amounts_and_ldp_impacts.sql` | Adds immutable leg, Cash/Security EUR amounts and six additive LDP-impact columns; initialises Cash and Titre fixtures and enforces leg values. |

Removed migrations belong to the unsupported older public/hybrid storage
architectures. Migrations are forward-only and applied in filename order by
`backend/scripts/apply_simulation_schema.py`.

## Frontend application

| File | Status | Current change |
|---|---|---|
| `frontend/src/App.tsx` | Heavily modified | Adds Workspace/Register navigation, date/version context, trade/FO/leg search, AG Grid lineage, single and batch adjustment, cancellation, proxy, preview, history, revert and reconciliation. The leg is a filter/read-only context and only its applicable amount is shown. |
| `frontend/src/api.ts` | Modified | Provides the typed browser boundary including leg-aware trade search and `/api/adjustment-options`. Mapping-table calls were removed. |
| `frontend/src/types.ts` | Expanded | Adds lineage, history, proxy, controlled options, Cash/Security amounts, leg and LDP impact fields. |
| `frontend/src/main.tsx` | Modified | Starts React Query and imports focused feature styles; obsolete mapping CSS is no longer imported. |
| `frontend/src/mapping.css` | Deleted | Removes searchable mapping popovers and the mapping-table viewer. |
| `frontend/src/workspace-actions.css` | Added/updated | Aligns search actions and selected-trade actions. |
| `frontend/src/styles.css` | Expanded/updated | Implements the CACIB minimalist layout, responsive forms and a five-column Find Trade grid aligned with Trade, FO system and Leg filters. |
| `frontend/src/batch.css` | Added | Styles AG Grid batch selection and per-trade editors. |
| `frontend/src/search-lineage.css` | Added | Styles compact lineage roles and active/cancelled states. |
| `frontend/src/revert.css` | Updated | Makes destructive revert actions red and links reverts to their commit. |

The former mock authentication components, CSS and tests were removed. Audit
uses the configured `AUDIT_ACTOR` until a production identity layer is designed.

## Mapping UI simplification

Previously, React could search distinct Parquet values and open mapping tables.
The current branch replaces that flow with:

```text
backend/app/project_config.py
    → GET /api/adjustment-options
    → ordinary frontend select
    → backend validation during preview/commit
    → controlledSelections in preview/history
```

Parquet remains internal to calculation functions only.

## Cash/Titre workflow

```text
User selects snapshot + FO system + leg
    → backend filters effective trades
    → selected trade retains immutable securityLegFlag
    → Cash row exposes cashAmountEur
      Titre row exposes securityAmountEur
    → preview recalculates EUR amount, buckets, LCR and LDP impacts
    → commit appends reversal + replacement with the same leg
```

Invalid combinations return a domain `422`: direct leg modification, Cash
amount on a Titre row, Titre amount on a Cash row, or both amounts together.

## Tests

| Test area | Current coverage |
|---|---|
| `test_adjustments.py` | Standard adjustment, additive reversal, Cash/Titre validation, bucket/LDP recalculation, cancellation, proxy, batch, concurrency, idempotency, lineage, filters and revert. |
| `test_enrichment_pipeline.py` | Cardinality, bucket rules, Cash/Titre selection, LDP rules, parameter matching, ambiguity and execution metadata. |
| `test_api_routes.py` | Public route contract, no authentication routes, configured options and safe database/configuration errors. |
| `test_mappings.py` | Internal manifest resolution and parameter-table errors. |
| `test_project_config.py` | Controlled options and invalid-value rejection. |
| `test_storage.py` | Retained storage composition and Cash/Security/LDP adapter mapping. |
| `test_simulation_reconciliation.py` | Recovery from output/metadata partial failure. |
| `test_data_dictionary.py` | Semantic uniqueness, labels, permissions and stage registration. |

Current verification:

```text
45 backend tests passed
frontend TypeScript build passed
Vite production build passed
generated field metadata is current
```

## Feature progression from `main`

1. Two-schema recoverable simulation storage.
2. Cancellation and proxy workflows.
3. Parquet-assisted mappings and later manifest-only parameter loading.
4. Cancelled-trade lineage and register/revert relationships.
5. Complete API and communication documentation.
6. FO-system batch selection and AG Grid trade views.
7. Registered DataFrame enrichment functions.
8. Central semantic field dictionary and generated frontend labels.
9. Removal of unsupported storage modes.
10. Removal of temporary authentication and role checks.
11. AI-friendly contributor guides and operational prompts.
12. Simplification from mapping-table UI to configured dropdowns.
13. Cash/Titre leg filtering, applicable EUR amount adjustment and LDP impacts.
14. Dedicated guide for adding future fields and filters safely.
