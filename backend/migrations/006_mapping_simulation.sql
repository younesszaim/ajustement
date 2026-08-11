BEGIN;

CREATE SCHEMA IF NOT EXISTS mapping_sim;

CREATE TABLE IF NOT EXISTS mapping_sim.mapping_registry (
    field_name text PRIMARY KEY,
    mapping_name text NOT NULL UNIQUE,
    display_name text NOT NULL,
    description text NOT NULL,
    source_path text NOT NULL,
    output_column text NOT NULL,
    producer_stage text NOT NULL,
    downstream_stages text[] NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mapping_sim.mapping_rows (
    mapping_name text NOT NULL REFERENCES mapping_sim.mapping_registry(mapping_name),
    row_number integer NOT NULL,
    row_payload jsonb NOT NULL,
    PRIMARY KEY(mapping_name,row_number),
    CHECK(jsonb_typeof(row_payload)='object')
);

INSERT INTO mapping_sim.mapping_registry(
    field_name,mapping_name,display_name,description,source_path,output_column,
    producer_stage,downstream_stages
) VALUES
('exposureClass','exposure_class_mapping','Exposure class','Possible outputs from the latest exposure-class mapping.',
 's3://limon-mappings/latest/exposure_class.parquet','EXPOSURE_CLASS','exposure_class',
 ARRAY['hqla','reporting_lines','lcr_impacts']),
('hqlaLevel','hqla_mapping','HQLA level','Possible outputs from the latest HQLA mapping.',
 's3://limon-mappings/latest/hqla.parquet','HQLA_LEVEL','hqla',
 ARRAY['reporting_lines','lcr_impacts']),
('reportingLineLcr','reporting_line_mapping','Reporting line LCR','Possible outputs from the latest reporting-line mapping.',
 's3://limon-mappings/latest/reporting_line.parquet','REPORTING_LINE_LCR','reporting_lines',
 ARRAY['lcr_impacts'])
ON CONFLICT(field_name) DO UPDATE SET
 mapping_name=EXCLUDED.mapping_name,display_name=EXCLUDED.display_name,
 description=EXCLUDED.description,source_path=EXCLUDED.source_path,
 output_column=EXCLUDED.output_column,producer_stage=EXCLUDED.producer_stage,
 downstream_stages=EXCLUDED.downstream_stages,is_active=true,loaded_at=now();

INSERT INTO mapping_sim.mapping_rows(mapping_name,row_number,row_payload) VALUES
('exposure_class_mapping',1,'{"INSTRUMENT_TYPE":"SECURITY","COUNTERPARTY_TYPE":"BANK","COUNTRY":"*","EXPOSURE_CLASS":"FINANCIAL"}'),
('exposure_class_mapping',2,'{"INSTRUMENT_TYPE":"SECURITY","COUNTERPARTY_TYPE":"SOVEREIGN","COUNTRY":"EU","EXPOSURE_CLASS":"SOVEREIGN"}'),
('exposure_class_mapping',3,'{"INSTRUMENT_TYPE":"LOAN","COUNTERPARTY_TYPE":"CORPORATE","COUNTRY":"*","EXPOSURE_CLASS":"CORPORATE"}'),
('exposure_class_mapping',4,'{"INSTRUMENT_TYPE":"DEPOSIT","COUNTERPARTY_TYPE":"CENTRAL_BANK","COUNTRY":"*","EXPOSURE_CLASS":"CENTRAL_BANK"}'),
('exposure_class_mapping',5,'{"INSTRUMENT_TYPE":"LOAN","COUNTERPARTY_TYPE":"RETAIL","COUNTRY":"*","EXPOSURE_CLASS":"RETAIL"}'),
('hqla_mapping',1,'{"EXPOSURE_CLASS":"SOVEREIGN","INSTRUMENT_TYPE":"SECURITY","RATING":"AAA-AA","HQLA_LEVEL":"L1"}'),
('hqla_mapping',2,'{"EXPOSURE_CLASS":"FINANCIAL","INSTRUMENT_TYPE":"SECURITY","RATING":"A","HQLA_LEVEL":"L2A"}'),
('hqla_mapping',3,'{"EXPOSURE_CLASS":"CORPORATE","INSTRUMENT_TYPE":"SECURITY","RATING":"BBB","HQLA_LEVEL":"L2B"}'),
('hqla_mapping',4,'{"EXPOSURE_CLASS":"*","INSTRUMENT_TYPE":"LOAN","RATING":"*","HQLA_LEVEL":"NON_HQLA"}'),
('reporting_line_mapping',1,'{"EXPOSURE_CLASS":"FINANCIAL","HQLA_LEVEL":"L1","MATURITY_BUCKET":"0-30D","REPORTING_LINE_LCR":"RL_SEC_01"}'),
('reporting_line_mapping',2,'{"EXPOSURE_CLASS":"FINANCIAL","HQLA_LEVEL":"L1","MATURITY_BUCKET":"31D+","REPORTING_LINE_LCR":"RL_SEC_03"}'),
('reporting_line_mapping',3,'{"EXPOSURE_CLASS":"CORPORATE","HQLA_LEVEL":"NON_HQLA","MATURITY_BUCKET":"*","REPORTING_LINE_LCR":"RL_LOAN_01"}'),
('reporting_line_mapping',4,'{"EXPOSURE_CLASS":"CENTRAL_BANK","HQLA_LEVEL":"L1","MATURITY_BUCKET":"*","REPORTING_LINE_LCR":"RL_DEP_01"}')
ON CONFLICT(mapping_name,row_number) DO UPDATE SET row_payload=EXCLUDED.row_payload;

ALTER TABLE adjustment_meta.item_snapshots
ADD COLUMN IF NOT EXISTS mapping_overrides jsonb NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS mapping_rows_payload_idx
ON mapping_sim.mapping_rows USING gin(row_payload);

REVOKE ALL ON SCHEMA mapping_sim FROM anon,authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA mapping_sim FROM anon,authenticated;

COMMIT;
