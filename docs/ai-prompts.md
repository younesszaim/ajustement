# Ready-to-use prompts for Codex and Claude

Start the AI tool from the repository root so it can discover `AGENTS.md` or
`CLAUDE.md` and their scoped instructions:

```bash
cd /path/to/ajustement_app
codex
# or
claude
```

Replace text inside `[brackets]`. The instructions are intentionally explicit
enough for a new agent while keeping the project files as the source of truth.

## Implement a feature end to end

```text
Implement the following feature: [describe the feature and expected user value].

Before editing:
1. Read AGENTS.md and every scoped AGENTS.md applicable to files you may change.
2. If you are Claude, read CLAUDE.md too.
3. Follow docs/change-workflow.md and the relevant docs/feature-playbooks.md section.
4. Read accepted decisions in docs/adr/ and preserve their invariants.
5. Inspect the existing implementation and tests; do not assume file ownership.

Define the expected behavior, affected layers, output journal/effective state if
business output changes, API contract, failure/retry behavior, frontend cache
effects, and tests. Resolve safe implementation details autonomously; ask me
only when a choice materially changes accounting, stored data, or user behavior.

Then implement the smallest complete end-to-end change, add regression tests,
update Swagger examples and documentation when relevant, and run make check.
Preserve unrelated working-tree changes. Do not commit or push until I ask.
```

## Plan a feature before coding

```text
Read AGENTS.md, the applicable scoped instructions, docs/change-workflow.md,
docs/feature-playbooks.md, and related ADRs.

Analyze this feature without editing files: [feature request].

Return:
- expected user behavior and acceptance criteria;
- accounting journal and effective-state rules, if applicable;
- affected backend, frontend, calculation, mapping, and storage files;
- API request/response changes;
- migration and compatibility needs;
- idempotency, concurrency, failure, retry, revert, and reconciliation behavior;
- React Query keys, draft state, dialogs, and cache invalidation;
- tests to add at each layer;
- unresolved decisions that genuinely require product input.

Prefer one recommended design and explain important tradeoffs concisely.
```

After accepting the plan:

```text
Proceed with the approved plan. Implement it completely, update tests and
documentation, run make check, and report behavior delivered, validation,
configuration/migrations, limitations, and working-tree status. Do not commit.
```

## Diagnose and fix a bug

```text
Diagnose and fix this problem: [expected behavior, actual behavior, reproduction,
error message, and relevant date/version/trade when known].

Read AGENTS.md, applicable scoped AGENTS.md, docs/change-workflow.md, and related
ADRs. Reproduce the issue and trace the owning layer: HTTP contract, domain
service, calculation pipeline, repository/coordinator, query key/invalidation,
local draft state, dialog stacking, or CSS.

Add the narrowest regression test that demonstrates the defect before or with
the fix. Implement the smallest complete root-cause correction; do not mask a
backend data error in the UI or use page refresh as synchronization. Verify
adjacent workflows sharing the affected code and run make check.

Preserve unrelated changes. Do not commit or push until I ask. In the handoff,
state the root cause, correction, tests, and any remaining risk.
```

## Add a frontend feature

```text
Read AGENTS.md and frontend/AGENTS.md completely, then follow
docs/change-workflow.md.

Add this frontend feature: [describe workflow and expected states].

Before editing, identify prerequisites, API/types changes, exact React Query
keys, server versus draft state, preview invalidation, idempotency-key ownership,
post-success invalidation, loading/empty/error/stale states, dialog layering,
keyboard accessibility, AG Grid constraints, and performance impact.

Keep authoritative calculations and reversal construction in the backend. Use
src/api.ts for HTTP, generated field labels, existing CACIB/shadcn patterns, and
targeted cache invalidation for new extracted workflows. Add focused Vitest
tests for high-risk transitions, run make check, and manually verify that the
workflow updates without page refresh. Do not commit or push.
```

## Fix a frontend problem

```text
Read AGENTS.md and frontend/AGENTS.md. Fix this frontend problem:
[reproduction, expected result, actual result, network response if known].

Inspect the request/response first. Classify the cause as API normalization,
query key, invalidation, local draft reset, retry identity, derived lineage,
overlay stacking, accessibility, or styling. Add a focused regression test and
fix the owning layer. Retain draft data on failed commits, expose backend detail
visibly, and do not require a browser refresh. Run make check and report the
root cause and adjacent workflows verified. Do not commit or push.
```

## Add a backend adjustment operation

```text
Read AGENTS.md, backend/AGENTS.md, applicable migration/enrichment AGENTS.md,
docs/change-workflow.md, docs/feature-playbooks.md, and accepted ADRs.

Add this adjustment operation: [describe operation].

First define its output journal, effective row after commit, preview result,
optimistic concurrency, idempotency, audit snapshots, history/lineage display,
revert semantics, partial-failure recovery, and Power BI additive effect.

Implement domain behavior before the thin API route. Keep preview and commit on
shared row-building logic, update repository contracts/adapters and forward-only
migrations only when required, add realistic Pydantic/Swagger examples, connect
typed frontend calls/UI, and test success, invalid input, stale state, retry,
lineage, revert, and reconciliation. Run make check. Do not commit or push.
```

## Add or rename a LiMon field

```text
Read AGENTS.md and the field playbook in docs/feature-playbooks.md.

Add or rename this field: [semantic meaning, current/new names, source, type,
editability, additivity, mapping/calculation role, and UI label].

Start from backend/config/data_dictionary.yaml. Trace API, database, Parquet,
calculation, filter, frontend, and historical snapshot representations. Do not
perform a blind repository-wide replacement and do not edit generated fields
manually. Add a forward migration for physical schema changes, preserve
compatibility where required, run make generate-fields, add relevant tests, and
run make check. Report every representation changed. Do not commit or push.
```

## Add a calculation or mapping stage

```text
Read AGENTS.md, backend/AGENTS.md, backend/lib/enrichments/AGENTS.md, the
calculation playbook, and ADR 0003.

Add this calculation stage: [business rule, input fields, outputs, mapping name
or rule-only behavior, downstream stages, and examples].

Implement a deterministic DataFrame function that preserves row count/order.
Parameter functions receive mapping DataFrames from the orchestrator and must
not read S3/files/databases themselves. Register inputs, outputs, type, mapping,
and dependencies explicitly; update dictionary/manifest/example Parquet when
needed. Test exact match, wildcard priority, ambiguity, null/no-match behavior,
cardinality, stage order, and execution metadata. Run make check. Do not commit.
```

## Review an existing change

```text
Review the current branch against its base branch. Read all repository
instructions first.

Focus on correctness and regressions: append-only accounting, active lineage,
idempotency, stale versions, partial commits/reconciliation, mapping validation,
API compatibility, React Query cache behavior, error visibility, accessibility,
and missing tests. Inspect actual diffs and relevant callers/tests.

Report findings ordered by severity with exact file/line references and concrete
failure scenarios. Do not modify files unless I explicitly ask for fixes. If no
issues are found, say so and identify residual test gaps.
```

## Adapt simulation to real Vertica and PostgreSQL

```text
Read AGENTS.md, backend/AGENTS.md, migration instructions, ADR 0001, and ADR
0002. Analyze this production adaptation: [describe Vertica connection/output
table and PostgreSQL metadata environment].

Preserve LimonOutputRepository and AdjustmentAuditRepository boundaries. Do not
join the stores or assume a distributed transaction. Define adapter mapping,
field-name translation, stable adjustment reference, idempotency reservation,
partial-failure states, reconciliation lookup, health checks, secret handling,
migration/deployment order, and rollback/recovery. Keep the simulation usable
for automated tests. Present a plan before making production-connectivity
changes unless I already explicitly authorized implementation.
```

## Update documentation after implementation

```text
Review the implemented change and update only the documentation it affects:
README setup/architecture, docs/api-testing-guide.md executable examples,
AGENTS.md/scoped instructions when contributor rules changed, feature playbooks,
testing strategy, and an ADR when an invariant or architecture decision changed.

Keep one canonical rule instead of duplicating conflicting instructions. Verify
all commands and file paths against the repository, run make check, and list the
documentation changed. Do not commit or push.
```

## Commit and push after approval

Use this only after reviewing the implementation:

```text
Run git status and inspect the complete diff. Run make check. Stage only files
belonging to the approved task; exclude secrets, .env, IDE files, build output,
and unrelated user files. Commit with a concise message describing the delivered
behavior, then push the current feature branch to origin. Report branch, commit
hash, validation, and remote tracking status. Do not merge into main.
```
