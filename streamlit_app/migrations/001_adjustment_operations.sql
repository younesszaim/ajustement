-- The simple architecture owns exactly one PostgreSQL table.
CREATE SCHEMA IF NOT EXISTS adjustment_simple;

CREATE TABLE IF NOT EXISTS adjustment_simple.adjustment_operations (
    operation_id uuid PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    operation_type text NOT NULL CHECK (operation_type IN ('REPLACE', 'CANCEL', 'REVERT', 'PROXY')),
    status text NOT NULL CHECK (status IN (
        'PENDING', 'COMMITTED', 'FAILED', 'RECONCILIATION_REQUIRED', 'REVERTED'
    )),
    asofdate date NOT NULL,
    version text NOT NULL,
    fo_system text NOT NULL,
    leg_flag smallint NOT NULL CHECK (leg_flag IN (0, 1)),
    source_output_id text,
    reason text NOT NULL,
    created_by text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_ids jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    committed_at timestamptz
);

CREATE INDEX IF NOT EXISTS adjustment_operations_context_idx
    ON adjustment_simple.adjustment_operations(asofdate, version, created_at DESC);
