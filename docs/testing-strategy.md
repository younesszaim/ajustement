# Testing strategy

Tests are executable architecture documentation. They should help a future
agent change one use case without breaking another.

## Test layers

| Layer | Purpose | Location |
|---|---|---|
| Domain | Accounting, versions, idempotency, operation interactions | `backend/tests/test_adjustments.py` |
| Calculation | DataFrame functions, mappings, DAG and metadata | enrichment/mapping tests |
| HTTP | Status codes, request contracts and safe errors | `backend/tests/test_api_routes.py` |
| Storage composition | Correct schemas and mandatory configuration | `backend/tests/test_storage.py` |
| Recovery | Partial commit and reconciliation without duplicates | reconciliation tests |
| Frontend unit | API error parsing, state helpers, focused components | colocated `*.test.ts(x)` files |
| Frontend build | Type compatibility and production bundling | `npm run build` |
| Database verification | Real SQL/adapters against disposable schemas | `verify_simulation.py` |

## Business scenario matrix

New changes should preserve all applicable scenarios:

| Scenario | Output journal | Effective state | Required protection |
|---|---|---|---|
| Standard adjustment | reversal + replacement | replacement active | version + idempotency |
| Second adjustment | reversal of current + replacement | newest replacement active | ordered lineage |
| Cancellation | reversal only | no active row | cannot adjust cancelled trade |
| Proxy | one generated proxy | proxy active | generated stable IDs |
| Multi-trade batch | journal per selected trade | one state per trade | batch atomic intent/retry |
| Revert | compensating audited journal | prior business effect restored | linked history |
| Partial commit | output may exist, metadata incomplete | reconciliation required | no duplicate output |
| Controlled override | normal journal + mapping metadata | replacement active | allowed value/version |

## Minimum tests for a mutation

- Preview has no write side effects.
- Commit output matches preview output.
- Expected version is required and stale versions fail.
- Reusing an idempotency key returns the original result.
- Invalid fields and values do not reach storage.
- Lineage ordering and active flags remain correct.
- History exposes committed, reverted, and reconciliation states consistently.
- Storage failure returns an actionable error and does not claim success.

## Frontend test growth

The repository currently permits an empty Vitest suite so `make check` remains
usable. Add focused tests whenever extracting or changing reusable behavior.
High-value first targets are:

1. API `detail` error normalization.
2. Query-key construction for snapshot-scoped reads.
3. Idempotency-key reset versus retry behavior.
4. Register action availability by commit/reconciliation status.
5. Original/reversal/replacement ordering and active tags.

Avoid testing AG Grid internals. Test the data transformation and component
contract around the grid.

## Commands

```bash
make test-backend
make test-frontend
make build-frontend
make check
```

For database-changing work, explicitly configure a disposable development
database before running:

```bash
cd backend
../.venv/bin/python scripts/verify_simulation.py
```
