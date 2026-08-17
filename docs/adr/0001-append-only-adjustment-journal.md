# ADR 0001: Append-only adjustment journal

- Status: Accepted
- Date: 2026-08-17
- Decision owners: LiMon adjustment team
- Supersedes: none

## Context

LiMon output feeds Power BI, where additive bucket columns must cancel
mathematically. Users also need complete evidence of who changed what and must
be able to undo a correction without erasing history.

## Decision

Business output is append-only. A standard adjustment appends a reversal of the
currently effective row and a recalculated replacement. Cancellation appends
only a reversal. Proxy creation appends a generated new trade. Revert is a new
compensating, linked, audited operation rather than a physical delete.

`record_type`, stable source/original references, batch reference, and lineage
ordering identify journal roles and the currently effective row.

## Alternatives considered

- Update the source row: rejected because it destroys the original fact and
  weakens Power BI/audit traceability.
- Store adjustments only in metadata: rejected because Power BI consumes the
  output table and must see reversal/replacement values.
- Physically delete reverted rows: rejected because deletion cannot be audited
  reliably and makes prior reports irreproducible.

## Consequences

Lineage grows with every adjustment and queries must resolve active state.
Storage requires append-only protections. Tests must cover repeated adjustment,
cancellation, proxy, revert, and mathematical cancellation of additive fields.

## Verification

Domain tests assert journal types/order, active rows, additive negation,
repeated operations, and linked revert history.

## Rollout and recovery

Schema changes are forward migrations. If output is written but metadata fails,
reconciliation uses the stable adjustment reference; output is never deleted or
inserted again merely to repair metadata.
