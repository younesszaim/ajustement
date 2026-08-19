-- Keep revert audit in the same single metadata table.
ALTER TABLE adjustment_simple.adjustment_operations
    ADD COLUMN IF NOT EXISTS reverts_operation_id uuid
        REFERENCES adjustment_simple.adjustment_operations(operation_id);

-- One committed adjustment can have only one revert intention. A failed revert
-- must be retried with its original idempotency key rather than recreated.
CREATE UNIQUE INDEX IF NOT EXISTS adjustment_operations_one_revert_idx
    ON adjustment_simple.adjustment_operations(reverts_operation_id)
    WHERE reverts_operation_id IS NOT NULL;
