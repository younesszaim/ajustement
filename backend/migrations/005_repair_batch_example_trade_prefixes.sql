-- Repair the first development seed, which labelled Murex examples OT-BATCH.
-- Scope is restricted to the ten known simulator fixture IDs; business rows
-- and committed adjustment rows are never touched.
BEGIN;

ALTER TABLE vertica_sim.output_completude_table
DISABLE TRIGGER output_sim_append_only;

UPDATE vertica_sim.output_completude_table
SET trade_no = 'MX-BATCH-' || (1000 + substring(output_record_id from 11)::integer)
WHERE output_record_id ~ '^SIM-BATCH-03[1-9]$|^SIM-BATCH-040$'
  AND fo_system = 'Murex'
  AND record_type = 'BASE'
  AND adjustment_reference IS NULL
  AND trade_no LIKE 'OT-BATCH-%';

ALTER TABLE vertica_sim.output_completude_table
ENABLE TRIGGER output_sim_append_only;

COMMIT;
