# Frontend operational guide

The root `AGENTS.md` applies. This file is the working contract for every file
under `frontend/`. Read it completely before changing UI behavior.

## Product responsibility

The frontend captures user intent, requests authoritative previews/commits, and
explains output lineage. It does not decide accounting, active state, mapping
validity, or recalculated values. Those belong to the backend.

The main user areas are:

1. Snapshot selection: exact `asofdate` plus `asofdateflow`.
2. Trade search: mandatory trade text and FO system, with bounded results.
3. Selected trade: current description, complete lineage, history, adjustment.
4. Adjustment workspace: draft, impact, controlled values, preview, commit.
5. Batch workspace: FO system, server filters, AG Grid selection, per-trade
   editing, aggregate preview, one commit.
6. Proxy workspace: user-entered new trade, backend-generated identifiers.
7. Adjustment register: committed/reverted/reconciliation entries and actions.

## File ownership

| File or area | Owns | Must not own |
|---|---|---|
| `src/main.tsx` | providers and global stylesheet imports | product state or API calls |
| `src/App.tsx` | top-level workflows, queries, mutations and dialog composition | backend calculations or SQL |
| `src/api.ts` | all browser HTTP calls and error normalization | React state or visual messages |
| `src/types.ts` | stable API request/response shapes | duplicated field labels |
| `src/generated/fields.ts` | generated field metadata | manual edits |
| `src/components/ui/` | reusable presentation primitives | LiMon workflow rules |
| feature CSS files | layout/visual state for the named feature | global resets or unrelated screens |

`App.tsx` is currently large. Do not make it larger by default. Extract a
component or hook when a new workflow has its own draft state, queries,
mutations, or more than one dialog. Keep orchestration near the top and pure
display components below or in focused files.

Suggested future extraction boundaries are `useAdjustmentWorkflow`,
`useBatchWorkflow`, `useRegisterActions`, `TradeSearchGrid`, and
`AdjustmentWorkspace`. Extract behavior with tests; do not perform a broad
rewrite as a side effect of an unrelated feature.

## Server state versus local state

React Query owns anything returned by FastAPI: dates/versions, FO systems,
mapping data, trade search/detail/lineage/history, and the global register.

Local React state owns temporary intent: selections, submitted filters, draft
changes/reasons, open dialogs, batch draft items, notices, and idempotency refs.

Never copy query data into local state merely to display it. Copy only when the
user begins an editable draft, and reset the draft when its context changes.

## Existing query-key contract

Keys include every value that changes the server result:

| Resource | Key |
|---|---|
| dates | `["dates"]` |
| mapped definitions | `["mapped-fields"]` |
| versions | `["versions", asofdate]` |
| searched trades | `["trades", context, submittedFilters, page]` |
| trade detail | `["trade", context, rowId]` |
| lineage | `["lineage", context, rowId]` |
| trade history | `["history", rowId]` |
| global register | `["global-history", dateFilter, flowFilter]` |
| register versions | `["global-versions", asofdate]` |
| calculation impact | `["impact", context, rowId, changes]` |
| mapping values | `["mapping-values", fieldName, search]` |
| mapping rows | `["mapping-rows", mappingName, search, page]` |
| FO systems | `["fo-systems", context]` |

Use serializable stable values. Never omit `asofdateflow` from a snapshot query.
Use `enabled` until prerequisites exist; do not send empty context and hide the
error. For new shared keys, prefer a typed factory:

```ts
const tradeKeys = {
  detail: (context: Context, rowId: string) => ["trade", context, rowId] as const,
  lineage: (context: Context, rowId: string) => ["lineage", context, rowId] as const,
  history: (rowId: string) => ["history", rowId] as const,
};
```

Do not migrate every existing key during an unrelated feature.

## Mutation lifecycle

Every durable workflow follows this state machine:

```text
draft changed
  → previous preview and retry key cleared
  → impact requested when applicable
  → authoritative preview requested
  → original/reversal/replacement shown
  → user supplies reason and confirms
  → commit sends preview rowVersion + stable idempotency key
  → success clears draft and refreshes affected server state
  → failure keeps editable intent and exposes backend detail
```

- Never construct or alter reversal/replacement values in React.
- Use the `rowVersion` returned by preview for optimistic concurrency.
- Disable duplicate submission while a mutation is pending.
- Preview becomes invalid after a field, row, context, or batch item changes.
- Do not display success before the commit response succeeds.
- On HTTP 409, keep input where possible and require a fresh preview.
- On timeout/503, preserve the retry key because output may already exist.

## Idempotency-key ownership

Retry identity belongs in `useRef`, never inline request generation.

| Workflow | Owner | Clear when | Preserve when |
|---|---|---|---|
| Adjustment/cancellation | `singleCommitKey` | draft/row/context change, success | same commit retry |
| Proxy | currently `singleCommitKey` | proxy field/draft ID change, success | same proxy retry |
| Batch | `batchCommitKey` | item/change changes, success | same batch retry |
| Revert | `revertCommitKey` | target/reason changes, success | same revert retry |
| Reconciliation | backend batch reference | no business key generated | retry same reference |

Current code shares `singleCommitKey` between single and proxy workflows. A
future extraction should separate them with regression tests. Generate lazily:

```ts
const key = commitKey.current ??= crypto.randomUUID();
```

Do not generate a new UUID for each `mutationFn` retry.

## Invalidation after writes

Current mutations use global `queryClient.invalidateQueries()`. This is correct
but broad. Preserve correctness; new/extracted workflows should target affected
resources after server success.

| Mutation | Search | Detail | Lineage | History | Register | Mapping |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Adjustment | yes | yes | yes | yes | yes | no |
| Cancellation | yes | yes | yes | yes | yes | no |
| Proxy | yes | if selected | yes | yes | yes | no |
| Batch | yes | affected | affected | affected | yes | no |
| Revert | yes | affected | yes | yes | yes | no |
| Reconciliation | normally no | if status shown | if status shown | yes | yes | no |

```ts
await Promise.all([
  queryClient.invalidateQueries({ queryKey: ["trades"] }),
  queryClient.invalidateQueries({ queryKey: ["trade"] }),
  queryClient.invalidateQueries({ queryKey: ["lineage"] }),
  queryClient.invalidateQueries({ queryKey: ["history"] }),
  queryClient.invalidateQueries({ queryKey: ["global-history"] }),
]);
```

Never reload the page or clear all cache as synchronization.

## Workflow-specific behavior

### Snapshot and trade search

- Changing date resets flow and row/batch context.
- Changing flow clears selection, submitted search, preview, and batch.
- Search requires trimmed trade text and FO system.
- Search is server-bounded and paginated; never request a whole snapshot.
- Clearing search removes submitted query and selection, not just input text.
- Clicking any lineage row opens the shared source trade and full lineage.

### Standard adjustment

- `changes` contains only values different from the original.
- Convert numeric drafts deliberately; do not silently turn empty into zero.
- A field change clears preview and single commit key.
- Impact is explanatory; preview is authoritative.
- Controlled fields use API-provided options and backend mapping metadata.
- Preview shows journal rows, changes, differences, mapping overrides, impacted
  stages, and recalculated fields without reimplementing calculations.

### Cancellation

- The visible action is “Cancel trade”; there is no separate preview button.
- An internal preview obtains reversal and row version before confirmation.
- Commit appends a reversal only; the cancelled trade remains visible for audit
  but has no active business row.

### Proxy

- The backend generates trade number and output record ID.
- `proxyDraftId` identifies one draft and changes after success or explicit reset.
- Editing proxy fields clears preview and commit retry key.
- Preview shows generated/recalculated output before commit.

### Batch

- Select one FO system before loading candidates.
- AG Grid filters translate to supported server filters; client filtering only
  refines the bounded page returned.
- Never mix another FO system or snapshot into the batch.
- Each item keeps its authoritative preview and `rowVersion`.
- Editing any item invalidates aggregate preview and batch retry key.
- Re-preview the entire batch after changes.
- One batch is one reason and one idempotency key.

### Register, revert and reconciliation

- Present a commit and linked revert as one audit relationship.
- Revert is red, requires reason/confirmation, and never means deletion.
- Offer revert only when backend history says the batch is revertible.
- `RECONCILIATION_REQUIRED` means output may exist while metadata is incomplete.
- Reconcile using the existing batch reference; never issue another business
  commit as recovery.

## AG Grid operational rules

- Register community modules once outside render.
- Memoize column definitions and derived rows.
- Use generated `fieldLabel()` for business headers.
- Match numeric/date filters to actual value types.
- Use physical output identity for row IDs when available; source `rowId` is not
  unique across lineage rows.
- Preserve order per trade: `BASE`, then each batch chronologically as
  `REVERSAL`, `ADJUSTED/PROXY`.
- Keep role/state tags compact and never hide inactive reversal rows.
- Do not embed large forms in cells; open the established workspace.
- Test row derivation/order, not AG Grid internals.

## Mapping controls

- Load options through `api.mappingValues`; never embed business options.
- Search/paginate mapping tables through the API; React never reads Parquet.
- Manual output selection does not rewrite upstream inputs.
- Show mapping name/source/output/downstream stages with compact hierarchy.
- Popovers stay in viewport and scroll internally.
- Backend validates selected values again even when chosen from the popup.

## HTTP client and error contract

All calls go through `src/api.ts`; components/hooks do not call `fetch`.

`json<T>` currently turns failed FastAPI responses into `Error(detail)`. When
extending it, format both string detail and validation arrays; never show
`[object Object]`. Preserve HTTP status in a typed API error when behavior must
distinguish 409 from 503.

Mutation errors must:

- set the shared notice to error mode;
- show the backend message with `role="alert"` and assertive live announcement;
- close only a confirmation layer that hides the message;
- retain draft and retry key until intent changes;
- never log secrets, raw database errors, or sensitive payloads.

## Dialogs, popovers and accessibility

- Confirmation dialogs remain above adjustment/batch/proxy workspaces. Inspect
  existing `dialog-layer.css` before adding z-index.
- Use a portal to `document.body` when ancestor overflow/stacking can clip a
  nested overlay.
- Escape closes only the topmost dismissible layer.
- Restore focus to the trigger where practical.
- Dialogs have accessible names, close actions, and explicit primary actions.
- Loading controls are disabled and visibly announce progress.
- Do not communicate active/cancelled/error state by color alone.
- Mapping and grid workflows remain keyboard reachable.

## Styling ownership

- Follow existing shadcn-style primitives and CACIB white/green patterns.
- Put feature rules in the named CSS file (`batch.css`, `mapping.css`,
  `trade-history.css`, etc.), not unrelated global files.
- Keep overlay stacking in `dialog-layer.css` or its owning overlay stylesheet.
- Reuse button/state classes. Destructive actions are red; normal primary
  actions use CACIB green.
- Avoid inline styles, duplicated component CSS, decorative cards without
  hierarchy, and oversized status tags.
- Verify narrow viewports and long business values.

## Performance constraints

- Never load all trades for a date/version.
- Preserve server filters, pagination, and query `enabled` guards.
- Memoize expensive lineage sorting and grid columns.
- Avoid rapidly changing query-key objects unless every change needs a request.
- Debounce mapping search if it would request on every keypress.
- Prefer targeted invalidation in extracted workflows.
- The bundle already triggers Vite's 500 kB warning. Lazy-load large future
  workspaces and assess new grid/chart dependencies before adding them.

## Testing expectations

Vitest is configured. Add focused `*.test.ts(x)` files. Test risk rather than
markup:

- API URL/body and error normalization;
- query keys contain exact context;
- editing clears preview and retry identity;
- failed commit retains draft and shows error;
- success invalidates affected resources;
- lineage order and active/cancelled tags;
- batch cannot cross FO system/context;
- confirmation is above workspace and keyboard dismissible.

Extract pure helpers for query keys, lineage sorting, and state transitions.
Mock the API boundary, not React Query or AG Grid internals. Avoid large snapshot
tests.

```bash
make test-frontend
make build-frontend
make check
```

The command currently permits an empty suite. New non-trivial frontend logic
must start growing tests rather than relying only on compilation.

## Checklist: add a frontend feature

1. Define prerequisites, user behavior, success, and failure states.
2. Identify affected resources and query keys.
3. Add stable API types in `types.ts`.
4. Add the encoded API call in `api.ts`; verify its shape in Swagger.
5. Decide server state versus local draft state.
6. Implement query guards and mutation lifecycle.
7. Define preview invalidation and retry-key reset/preserve rules.
8. Define targeted success invalidation.
9. Reuse generated labels, UI primitives, theme, and overlay layers.
10. Cover loading, empty, error, disabled, success, and stale states.
11. Test high-risk transitions and API integration.
12. Run `make check` and exercise the workflow without refresh.

## Checklist: fix a frontend bug

1. Reproduce it and inspect network request/response.
2. Classify API contract, cache key, invalidation, local draft, derived rows,
   overlay stacking, or CSS as the owning cause.
3. Add a failing test around the smallest extractable behavior.
4. Fix the owner; do not mask backend data issues in presentation.
5. Verify adjacent workflows sharing the component/ref/query family.
6. Test error, retry, context change, and refresh-free recovery.
7. Run `make check` and report root cause, not only symptom.

## Prohibited patterns

- Direct `fetch` outside `api.ts`.
- Client-side authoritative calculation or reversal construction.
- Snapshot query keys without version.
- New idempotency UUID on every retry.
- Page reload as mutation synchronization.
- Swallowed API failure displayed as empty/success.
- Unbounded snapshot loaded into AG Grid.
- Hard-coded business labels or mapping values.
- Manual edits to generated field metadata.
- Physical-delete language for revert.
- Application role checks while this branch has no authentication.
- Opportunistic full rewrite of `App.tsx` during unrelated work.
