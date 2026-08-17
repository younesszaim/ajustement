# Backend contributor rules

The root `AGENTS.md` applies. This file adds backend-specific rules.

## Layer boundaries

- `app/main.py`: parse HTTP input, call a service/repository, translate errors.
  Do not construct adjustment rows here.
- `app/models.py`: Pydantic HTTP contracts with realistic Swagger examples.
- `app/services.py`: business rules shared by preview and commit.
- `app/domain/repositories.py`: storage abstractions used by services.
- `app/adapters/`: SQL and coordination details behind those abstractions.
- `lib/enrichments/`: DataFrame-only business calculations.

Dependency direction is HTTP → service → repository contract → adapter. An
adapter must not import FastAPI, and calculation functions must not call SQL.

## Error contract

- Invalid business input: `DomainError`, exposed as HTTP 422.
- Stale versions or incompatible state: `ConflictError`, HTTP 409.
- Storage/coordinator failure: `InfrastructureError`, HTTP 503.
- Pydantic request validation remains the standard structured HTTP 422.
- Do not expose connection strings, SQL text, credentials, or stack traces.

## Adjustment implementation

- Build previews through the same service helpers used by commit.
- Re-read effective rows immediately before durable writes.
- Store immutable snapshots sufficient for reconciliation and audit.
- Keep idempotency references deterministic across recovery.
- Negate only fields declared additive by the semantic dictionary.
- Validate controlled mapping selections again in the backend.

## Tests

Use repository fakes for domain behavior and targeted adapter tests for storage
coordination. A new mutation normally needs tests for preview, commit,
idempotent retry, stale version, invalid field/value, lineage, and revert.

Run from the repository root:

```bash
make test-backend
```
