-- Only required for the Supabase simulation output table.
-- The simple app stores lineage on the output row and does not use
-- vertica_sim.output_adjustment_links.
ALTER TABLE vertica_sim.output_completude_table
    ADD COLUMN IF NOT EXISTS source_output_record_id text,
    ADD COLUMN IF NOT EXISTS parent_output_record_id text;

-- One-time compatibility backfill for adjustments created by the old app.
-- The new Streamlit runtime never reads output_adjustment_links.
ALTER TABLE vertica_sim.output_completude_table DISABLE TRIGGER output_sim_append_only;

UPDATE vertica_sim.output_completude_table output
SET source_output_record_id = links.source_output_record_id,
    parent_output_record_id = links.parent_output_record_id
FROM vertica_sim.output_adjustment_links links
WHERE links.output_record_id = output.output_record_id
  AND output.source_output_record_id IS NULL;

ALTER TABLE vertica_sim.output_completude_table ENABLE TRIGGER output_sim_append_only;
