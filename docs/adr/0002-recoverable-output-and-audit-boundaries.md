# ADR 0002: Recoverable output and audit boundaries

- Status: Accepted
- Date: 2026-08-17
- Decision owners: LiMon adjustment team
- Supersedes: none

## Context

The production target stores business output in Vertica and adjustment
metadata in PostgreSQL. Local simulation uses one PostgreSQL database but must
preserve the same communication boundary and partial-failure behavior.

## Decision

Output and metadata are accessed through separate repository protocols. The
simulation implements them with `vertica_sim` and `adjustment_meta` schemas and
a coordinator that reserves an idempotency request, stages intent, appends
output, then finalizes metadata.

The application never joins the two schemas as a shortcut. A failure after
output commit produces `RECONCILIATION_REQUIRED`; reconciliation locates rows by
stable adjustment reference and completes metadata idempotently.

## Alternatives considered

- One cross-schema transaction: rejected because it cannot model Vertica plus
  PostgreSQL production behavior.
- Best-effort dual writes without recovery state: rejected because output could
  exist without visible/auditable history.
- Roll back by deleting output: rejected by the append-only journal decision.

## Consequences

Commit coordination is more explicit and must test each failure point. Adapter
contracts remain replaceable when `vertica_sim` becomes a real Vertica client.

## Verification

Reconciliation tests inject failure after output commit, retry the request,
assert no duplicate rows, and verify finalized history.

## Rollout and recovery

Deploy metadata migrations before enabling new coordinator fields. Recovery is
safe only when every output row carries a stable adjustment reference.
