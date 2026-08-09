# Real LiMon storage architecture

## Ownership

| Data | System of record |
|---|---|
| `output_completude_table` base rows | Vertica |
| cancellation and replacement output rows | Vertica |
| effective trade and physical lineage | Vertica |
| adjustment command/idempotency state | PostgreSQL/Supabase |
| adjustment batch metadata and snapshots | PostgreSQL/Supabase |
| field changes and user-action events | PostgreSQL/Supabase |

The React client talks only to FastAPI. It never connects to either database.

## Commit protocol

1. FastAPI re-reads every current effective row from Vertica.
2. It validates row versions and recalculates with production LiMon Python code.
3. PostgreSQL reserves an idempotent `adjustment_requests` row in `PENDING` state.
4. Vertica inserts all cancellation/replacement rows in one Vertica transaction, using the PostgreSQL-generated batch reference.
5. PostgreSQL marks the request `VERTICA_COMMITTED` and writes immutable batch/item/change snapshots.
6. PostgreSQL marks the request `COMMITTED`.

If the process stops after step 4, a recovery worker queries Vertica by the unique batch reference and completes PostgreSQL metadata. Never automatically reverse an uncertain transaction.

## Integration points

- Implement `VerticaLimonRepository` with the existing enterprise connection utility.
- Customize only `VerticaColumnMap` and the domain mapper for physical column names.
- Complete the three snapshot queries and `finalize_request()` in `PostgresAuditRepository`.
- Replace `MockCalculationAdapter` with imports from the production LiMon pipeline.
- Configure `STORAGE_MODE=hybrid`, `SUPABASE_DB_URL`, and enterprise Vertica secrets.

## Idempotency requirements

Vertica must enforce or emulate uniqueness for:

```text
batch_reference + source_row_id + record_type
```

This makes coordinator retries safe. PostgreSQL separately enforces one request per project/idempotency key.
