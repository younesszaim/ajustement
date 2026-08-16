-- Mapping rows are read from manifest-selected Parquet files.
-- PostgreSQL stores only the mapping reference selected during an adjustment.
BEGIN;

-- Remove the legacy PostgreSQL mapping registry and copied mapping rows.
DROP SCHEMA IF EXISTS mapping_sim CASCADE;

ALTER TABLE adjustment_meta.item_snapshots
ADD COLUMN IF NOT EXISTS mapping_overrides jsonb NOT NULL DEFAULT '[]';

COMMIT;
