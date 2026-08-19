-- Review types and VARCHAR lengths with the LiMon DBA before applying.
-- bi_id is reused as the unique output row identifier for BASE and generated rows.
ALTER TABLE public.output_completude_table ADD COLUMN IF NOT EXISTS record_type VARCHAR(16) DEFAULT 'BASE';
ALTER TABLE public.output_completude_table ADD COLUMN IF NOT EXISTS adjustment_reference VARCHAR(100);
ALTER TABLE public.output_completude_table ADD COLUMN IF NOT EXISTS source_output_record_id VARCHAR(100);
ALTER TABLE public.output_completude_table ADD COLUMN IF NOT EXISTS parent_output_record_id VARCHAR(100);
