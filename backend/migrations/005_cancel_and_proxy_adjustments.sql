BEGIN;

-- Adjustment operations no longer have a fixed two-row journal shape:
-- MODIFY/REVERT = reversal + replacement, CANCELLATION = reversal, PROXY = proxy.
DO $$
DECLARE constraint_row record;
BEGIN
    FOR constraint_row IN
        SELECT n.nspname, t.relname, c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE c.contype='c'
          AND n.nspname IN ('adjustment_meta','vertica_sim')
          AND (
            (t.relname='requests' AND pg_get_constraintdef(c.oid) LIKE '%action_type%')
            OR (t.relname='batches' AND pg_get_constraintdef(c.oid) LIKE '%action_type%')
            OR (t.relname='batches' AND pg_get_constraintdef(c.oid) LIKE '%inserted_record_count%')
            OR (t.relname='output_completude_table' AND pg_get_constraintdef(c.oid) LIKE '%record_type%')
            OR (t.relname='output_adjustment_links' AND pg_get_constraintdef(c.oid) LIKE '%record_type%')
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I DROP CONSTRAINT %I',
            constraint_row.nspname,constraint_row.relname,constraint_row.conname
        );
    END LOOP;
END $$;

ALTER TABLE adjustment_meta.requests
    ADD CONSTRAINT requests_operation_type_check
    CHECK(action_type IN ('ADJUSTMENT','TRADE_CANCELLATION','PROXY','REVERT'));

ALTER TABLE adjustment_meta.batches
    ADD CONSTRAINT batches_operation_type_check
    CHECK(action_type IN ('ADJUSTMENT','TRADE_CANCELLATION','PROXY','REVERT')),
    ADD CONSTRAINT batches_variable_output_count_check
    CHECK(trade_count > 0 AND inserted_record_count >= trade_count);

ALTER TABLE adjustment_meta.item_snapshots
    ALTER COLUMN parent_output_record_id DROP NOT NULL,
    ALTER COLUMN cancellation_output_record_id DROP NOT NULL,
    ALTER COLUMN replacement_output_record_id DROP NOT NULL,
    ALTER COLUMN original_snapshot DROP NOT NULL,
    ALTER COLUMN cancellation_snapshot DROP NOT NULL,
    ALTER COLUMN replacement_snapshot DROP NOT NULL;

ALTER TABLE vertica_sim.output_completude_table
    ADD CONSTRAINT output_sim_record_type_check
    CHECK(record_type IN ('BASE','ADJUSTMENT_CANCEL','ADJUSTMENT_REPLACEMENT','PROXY')),
    ADD CONSTRAINT output_sim_adjustment_reference_check
    CHECK((record_type='BASE' AND adjustment_reference IS NULL) OR
          (record_type<>'BASE' AND adjustment_reference IS NOT NULL));

ALTER TABLE vertica_sim.output_adjustment_links
    ALTER COLUMN parent_output_record_id DROP NOT NULL,
    ADD CONSTRAINT output_links_record_type_check
    CHECK(record_type IN ('ADJUSTMENT_CANCEL','ADJUSTMENT_REPLACEMENT','PROXY'));

COMMIT;
