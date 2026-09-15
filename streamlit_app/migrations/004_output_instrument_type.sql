-- Supabase development simulation only. Existing examples are classified SEC
-- so the dispatcher never chooses a pipeline silently at runtime.
ALTER TABLE vertica_sim.output_completude_table
    ADD COLUMN IF NOT EXISTS instrument_type text;

UPDATE vertica_sim.output_completude_table
SET instrument_type = 'SEC'
WHERE instrument_type IS NULL;

ALTER TABLE vertica_sim.output_completude_table
    ALTER COLUMN instrument_type SET NOT NULL;

ALTER TABLE vertica_sim.output_completude_table
    DROP CONSTRAINT IF EXISTS output_completude_instrument_type_chk;

ALTER TABLE vertica_sim.output_completude_table
    ADD CONSTRAINT output_completude_instrument_type_chk
    CHECK (instrument_type IN ('OST', 'SEC', 'EQUITY'));
