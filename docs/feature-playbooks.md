# Feature development playbooks

Use these checklists to keep backend, frontend, storage, and documentation in
sync. Not every feature needs every step; skipped steps should be intentional.

## Add or rename a business field

1. Update `backend/config/data_dictionary.yaml` with semantic ID, API name,
   physical names, label, type, editability, additivity, and dependencies.
2. Update mapping configuration and calculation registry if it participates in
   enrichment.
3. Add a forward migration when a physical database column changes.
4. Run `make generate-fields`; never hand-edit generated TypeScript.
5. Update Pydantic/frontend types only if the field changes a structured API.
6. Add dictionary, calculation, adapter, and UI tests as applicable.

## Add an API endpoint

1. Add request/response models and realistic Swagger examples.
2. Add domain/repository behavior before composing the thin route.
3. Translate known errors consistently in `main.py`.
4. Add a typed method in `frontend/src/api.ts` and types in `types.ts`.
5. Use React Query with fully scoped keys and invalidation after writes.
6. Add API route examples to `docs/api-testing-guide.md`.
7. Test success, invalid request, domain error, conflict, and infrastructure
   failure where relevant.

## Add an adjustment operation

1. Define its accounting journal: number/type of appended output rows and which
   row, if any, becomes effective.
2. Implement preview and commit through shared service helpers.
3. Define version checking, idempotency, lineage, revert, and reconciliation.
4. Persist reason, actor, immutable snapshots, field changes, and references.
5. Add UI drafting, understandable preview, confirmation, errors, and refresh.
6. Test repeated adjustments on one row and operation interactions.

## Add a calculation stage

1. Choose a pure rule function or parameter-driven function.
2. Implement against DataFrames without changing cardinality/order.
3. Register declared inputs/outputs and mapping dependency.
4. Add stage dependencies and field dependency starts.
5. Add or version Parquet examples and update the latest manifest.
6. Test exact/wildcard/ambiguous/no-match cases and execution metadata.

## Add a migration

1. Read `backend/migrations/AGENTS.md`.
2. Create the next ordered file; do not rewrite applied SQL.
3. Preserve append-only and schema-isolation protections.
4. Update adapters and schema installer assumptions.
5. Document deployment order, data backfill, and rollback/recovery guidance.
6. Validate against a disposable development database.

## Diagnose a frontend mutation that appears to do nothing

1. Verify the browser network response and backend `detail` message.
2. Confirm the mutation has visible `onError` handling.
3. Check dialog stacking and that the error notice is not behind a modal.
4. Confirm the idempotency key survives retry but resets after draft edits.
5. Confirm success invalidates every affected query.
6. Refresh only as a diagnostic; a correct UI must update without reload.
