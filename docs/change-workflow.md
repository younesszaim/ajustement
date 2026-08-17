# Change workflow for features and fixes

This workflow is designed for Codex, Claude, and new developers. It makes
changes predictable without forcing every task through the entire codebase.

## 1. Translate the request into behavior

Write a short internal contract before editing:

- Who performs the action?
- What snapshot, trade, batch, or mapping is in scope?
- What must the user see before and after the action?
- Which output rows should be appended?
- Which metadata and audit events should be recorded?
- What can fail, and how should retry behave?
- What existing behavior must remain unchanged?

For a bug, also capture expected versus actual behavior and the smallest known
reproduction. Do not treat a symptom such as “refresh fixes it” as the cause.

## 2. Build an impact map

Use this table to locate the smallest complete change:

| Change signal | Inspect first | Common downstream files |
|---|---|---|
| HTTP payload or response | `app/models.py`, `app/main.py` | `src/api.ts`, `src/types.ts`, Swagger guide |
| Adjustment accounting | `app/services.py` | repository contracts, coordinator, lineage tests |
| Persistence or recovery | repository protocols and adapters | migration, reconciliation tests, health/errors |
| Business column | data dictionary | generated fields, adapter translation, mappings |
| Calculation result | enrichment registry and dependencies | rule/parameter function, Parquet, pipeline tests |
| Search/filter behavior | output repository | request model, API client, React Query key, AG Grid |
| Stale frontend data | mutation callbacks/query keys | API errors, cache invalidation, dialog state |
| Visual behavior | owning React component | existing CSS/theme file, accessibility behavior |

Search for the semantic field ID and API name before searching for a physical
database name. A physical column may intentionally differ across API, DB, and
Parquet.

## 3. Establish a regression guard

For a bug fix, add the narrowest failing test that proves the defect whenever
the layer is testable. For a feature, define acceptance examples before the
implementation:

- one successful scenario;
- one invalid-input scenario;
- one stale/conflicting-state scenario for writes;
- one repeated/retry scenario for durable mutations;
- one lineage/history scenario when output changes.

Avoid snapshot tests for accounting data. Assert the important values, row
types, active state, IDs, version behavior, and audit status explicitly.

## 4. Implement from the domain outward

For behavior that crosses layers, use this order:

1. Semantic configuration and domain/request contracts.
2. Service behavior and unit tests.
3. Repository protocol, adapter, and migration if required.
4. Thin API route and HTTP tests.
5. Typed frontend API and response shapes.
6. React Query mutation/query behavior and UI.
7. API examples and architecture documentation.

Pure UI changes may start in the owning component. Storage-only operational
fixes may remain in adapters. Do not add empty layers just to follow the list.

## 5. Review cross-cutting risks

Before validation, answer these questions:

- Does preview produce exactly the rows commit will write?
- Is the active row unambiguous after the operation?
- Does retry avoid duplicate rows?
- Does stale preview return a conflict instead of overwriting newer state?
- Can reconciliation recover a partial cross-schema commit?
- Are Power BI additive measures mathematically neutralized by reversals?
- Are mapping selections validated and their versions audited?
- Does the UI show backend errors without requiring refresh?
- Are all affected queries invalidated after success?
- Did a field rename bypass the semantic dictionary?

## 6. Validate and hand off

Run `make check`. Run database verification only when the task changes SQL,
adapters, idempotency, or reconciliation and a disposable database is clearly
configured.

The completion report should state:

- observable behavior delivered;
- important implementation decisions;
- tests and commands executed;
- migrations/configuration required;
- known limitations or follow-up work;
- whether changes are committed or only present in the working tree.

Do not report success when tests did not run. State the exact blocker and what
was verified instead.

## Fix-specific diagnostic paths

### API returns 422

Compare the URL/body with the Pydantic model, including date versus datetime
types and camelCase names. If validation passes, inspect `DomainError` from the
service. Preserve FastAPI's structured validation response.

### API returns 503

Classify configuration, DNS, credentials, and coordinator failures separately.
Check both schema health results. Never convert a database outage into an empty
successful list because that hides data loss from the UI.

### Commit exists after refresh but history is missing

Treat it as a partial commit. Inspect the idempotency request and stable output
reference, then reconciliation. Do not insert output a second time.

### UI reports success incorrectly or shows no error

Inspect the network response, mutation `onError`, shared notice state, and modal
stacking. A mutation is successful only after an HTTP success response.

### Wrong calculated value

Trace changed fields → dependency resolver → ordered registry stages → exact
rule/mapping function → selected Parquet version → execution metadata. Do not
patch the displayed result in React.
