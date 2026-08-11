BEGIN;

CREATE SCHEMA IF NOT EXISTS vertica_sim;
CREATE SCHEMA IF NOT EXISTS adjustment_meta;

CREATE TABLE IF NOT EXISTS adjustment_meta.projects (
    project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_key text NOT NULL UNIQUE,
    display_name text NOT NULL,
    output_table_name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS adjustment_meta.requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES adjustment_meta.projects(project_id),
    idempotency_key text NOT NULL,
    batch_reference text NOT NULL,
    action_type text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING',
    base_asofdate date NOT NULL,
    base_asofdateflow timestamp without time zone NOT NULL,
    reason text NOT NULL,
    requested_by text NOT NULL,
    item_count integer NOT NULL,
    reverted_adjustment_batch_id uuid,
    output_record_ids text[] NOT NULL DEFAULT '{}',
    request_payload jsonb NOT NULL DEFAULT '[]',
    error_code text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id,idempotency_key),
    UNIQUE(project_id,batch_reference),
    CHECK(action_type IN ('ADJUSTMENT','REVERT')),
    CHECK(status IN ('PENDING','OUTPUT_COMMITTED','COMMITTED','FAILED','RECONCILIATION_REQUIRED')),
    CHECK(length(btrim(reason)) >= 5),
    CHECK(item_count > 0)
);

ALTER TABLE adjustment_meta.requests
ADD COLUMN IF NOT EXISTS request_payload jsonb NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS adjustment_meta.batches (
    adjustment_batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES adjustment_meta.projects(project_id),
    batch_reference text NOT NULL,
    action_type text NOT NULL,
    status text NOT NULL DEFAULT 'COMMITTED',
    base_asofdate date NOT NULL,
    base_asofdateflow timestamp without time zone NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    reverted_adjustment_batch_id uuid REFERENCES adjustment_meta.batches(adjustment_batch_id),
    idempotency_key text NOT NULL,
    trade_count integer NOT NULL,
    inserted_record_count integer NOT NULL,
    UNIQUE(project_id,batch_reference),
    UNIQUE(project_id,idempotency_key),
    CHECK(action_type IN ('ADJUSTMENT','REVERT')),
    CHECK(status = 'COMMITTED'),
    CHECK(inserted_record_count = trade_count * 2)
);

CREATE TABLE IF NOT EXISTS adjustment_meta.item_snapshots (
    snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    adjustment_batch_id uuid NOT NULL REFERENCES adjustment_meta.batches(adjustment_batch_id),
    source_output_record_id text NOT NULL,
    parent_output_record_id text NOT NULL,
    cancellation_output_record_id text NOT NULL,
    replacement_output_record_id text NOT NULL,
    trade_no text,
    fo_system text NOT NULL,
    expected_row_version text NOT NULL,
    original_snapshot jsonb NOT NULL,
    cancellation_snapshot jsonb NOT NULL,
    replacement_snapshot jsonb NOT NULL,
    changed_fields jsonb NOT NULL DEFAULT '[]',
    recalculated_fields jsonb NOT NULL DEFAULT '[]',
    impacted_stages jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(adjustment_batch_id,source_output_record_id)
);

CREATE TABLE IF NOT EXISTS adjustment_meta.field_changes (
    field_change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES adjustment_meta.item_snapshots(snapshot_id),
    field_name text NOT NULL,
    old_value jsonb,
    new_value jsonb,
    value_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(snapshot_id,field_name)
);

CREATE TABLE IF NOT EXISTS adjustment_meta.action_events (
    action_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id uuid NOT NULL REFERENCES adjustment_meta.projects(project_id),
    adjustment_batch_id uuid REFERENCES adjustment_meta.batches(adjustment_batch_id),
    source_output_record_id text,
    event_type text NOT NULL,
    event_status text NOT NULL DEFAULT 'SUCCESS',
    actor_user_id text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    asofdate date,
    asofdateflow timestamp without time zone,
    event_metadata jsonb NOT NULL DEFAULT '{}',
    CHECK(event_status IN ('SUCCESS','FAILED','DENIED'))
);

CREATE TABLE IF NOT EXISTS vertica_sim.output_completude_table (
    output_record_id text PRIMARY KEY,
    asofdate date NOT NULL,
    asofdateflow timestamp without time zone NOT NULL,
    trade_no text NOT NULL,
    fo_system text NOT NULL,
    isin text,
    portfolio text,
    counterparty text,
    target_instrument_type text,
    issue text,
    maturity_date date,
    value_date date,
    currency text,
    amount numeric(38,10),
    eur_amount_0d numeric(38,10),
    eur_amount_7d numeric(38,10),
    eur_amount_30d numeric(38,10),
    eur_amount_3m numeric(38,10),
    lcr_inflow numeric(38,10),
    lcr_outflow numeric(38,10),
    reserve_amount numeric(38,10),
    exposure_class text,
    hqla_level text,
    reporting_line_lcr text,
    record_type text NOT NULL DEFAULT 'BASE',
    adjustment_reference text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL DEFAULT 'limon-pipeline',
    CHECK(record_type IN ('BASE','ADJUSTMENT_CANCEL','ADJUSTMENT_REPLACEMENT')),
    CHECK((record_type='BASE' AND adjustment_reference IS NULL) OR
          (record_type<>'BASE' AND adjustment_reference IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS vertica_sim.output_adjustment_links (
    output_record_id text PRIMARY KEY REFERENCES vertica_sim.output_completude_table(output_record_id),
    source_output_record_id text NOT NULL,
    parent_output_record_id text NOT NULL,
    adjustment_reference text NOT NULL,
    record_type text NOT NULL,
    item_position integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(adjustment_reference,source_output_record_id,record_type),
    CHECK(record_type IN ('ADJUSTMENT_CANCEL','ADJUSTMENT_REPLACEMENT'))
);

CREATE INDEX IF NOT EXISTS output_sim_context_idx ON vertica_sim.output_completude_table(asofdate,asofdateflow,fo_system,trade_no);
CREATE INDEX IF NOT EXISTS output_sim_reference_idx ON vertica_sim.output_completude_table(adjustment_reference);
CREATE INDEX IF NOT EXISTS output_sim_source_idx ON vertica_sim.output_adjustment_links(source_output_record_id,created_at);
CREATE INDEX IF NOT EXISTS meta_batches_context_idx ON adjustment_meta.batches(project_id,base_asofdate,base_asofdateflow,created_at DESC);
CREATE INDEX IF NOT EXISTS meta_snapshots_source_idx ON adjustment_meta.item_snapshots(source_output_record_id,created_at DESC);
CREATE INDEX IF NOT EXISTS meta_requests_recovery_idx ON adjustment_meta.requests(status,updated_at);

INSERT INTO adjustment_meta.projects(project_key,display_name,output_table_name)
VALUES('limon_ldp_bmf','LiMon LDP BMF Hybrid Simulation','vertica_sim.output_completude_table')
ON CONFLICT(project_key) DO UPDATE SET display_name=EXCLUDED.display_name,output_table_name=EXCLUDED.output_table_name,is_active=true;

INSERT INTO vertica_sim.output_completude_table(
    output_record_id,asofdate,asofdateflow,trade_no,fo_system,isin,portfolio,counterparty,
    target_instrument_type,issue,maturity_date,value_date,currency,amount,eur_amount_0d,
    eur_amount_7d,eur_amount_30d,eur_amount_3m,lcr_inflow,lcr_outflow,reserve_amount,
    exposure_class,hqla_level,reporting_line_lcr,record_type
) VALUES
('SIM-ROW-0001','2026-08-06','2026-08-07 11:14:09','OT-982731','Orchestrade','FR0012345678','LIQUIDITY','CP_BANK_01','SECURITY','ISSUER_A','2026-08-20','2026-08-06','EUR',1000000,1000000,0,1000000,0,0,200000,0,'FINANCIAL','L1','RL_SEC_01','BASE'),
('SIM-ROW-0002','2026-08-06','2026-08-07 11:14:09','MX-441082','Murex','DE000A1EWWW0','LIQUIDITY','CP_BANK_02','SECURITY','ISSUER_B','2026-09-20','2026-08-06','EUR',750000,750000,0,0,750000,0,150000,0,'FINANCIAL','L1','RL_SEC_03','BASE'),
('SIM-ROW-0003','2026-08-06','2026-08-07 04:45:02','KD-109221','Kondor','GB00B03MLX29','LIQUIDITY','CP_BANK_03','DEPOSIT','ISSUER_C','2026-08-12','2026-08-06','EUR',2400000,2400000,2400000,0,0,0,480000,0,'FINANCIAL','NON_HQLA','RL_SEC_01','BASE'),
('SIM-ROW-0004','2026-08-05','2026-08-06 06:12:00','SP-830114','SOPHIS','US0378331005','LIQUIDITY','CP_BANK_04','SECURITY','ISSUER_D','2026-08-19','2026-08-05','EUR',320000,320000,0,320000,0,0,64000,0,'FINANCIAL','L1','RL_SEC_01','BASE')
ON CONFLICT(output_record_id) DO NOTHING;

DROP TRIGGER IF EXISTS output_sim_append_only ON vertica_sim.output_completude_table;
CREATE TRIGGER output_sim_append_only BEFORE UPDATE OR DELETE
ON vertica_sim.output_completude_table FOR EACH ROW
EXECUTE FUNCTION public.prevent_adjustment_mutation();

DROP TRIGGER IF EXISTS output_sim_links_append_only ON vertica_sim.output_adjustment_links;
CREATE TRIGGER output_sim_links_append_only BEFORE UPDATE OR DELETE
ON vertica_sim.output_adjustment_links FOR EACH ROW
EXECUTE FUNCTION public.prevent_adjustment_mutation();

DROP TRIGGER IF EXISTS meta_batches_append_only ON adjustment_meta.batches;
CREATE TRIGGER meta_batches_append_only BEFORE UPDATE OR DELETE
ON adjustment_meta.batches FOR EACH ROW
EXECUTE FUNCTION public.prevent_adjustment_mutation();

DROP TRIGGER IF EXISTS meta_snapshots_append_only ON adjustment_meta.item_snapshots;
CREATE TRIGGER meta_snapshots_append_only BEFORE UPDATE OR DELETE
ON adjustment_meta.item_snapshots FOR EACH ROW
EXECUTE FUNCTION public.prevent_adjustment_mutation();

DROP TRIGGER IF EXISTS meta_changes_append_only ON adjustment_meta.field_changes;
CREATE TRIGGER meta_changes_append_only BEFORE UPDATE OR DELETE
ON adjustment_meta.field_changes FOR EACH ROW
EXECUTE FUNCTION public.prevent_adjustment_mutation();

DROP TRIGGER IF EXISTS meta_events_append_only ON adjustment_meta.action_events;
CREATE TRIGGER meta_events_append_only BEFORE UPDATE OR DELETE
ON adjustment_meta.action_events FOR EACH ROW
EXECUTE FUNCTION public.prevent_adjustment_mutation();

REVOKE ALL ON SCHEMA vertica_sim,adjustment_meta FROM anon,authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA vertica_sim,adjustment_meta FROM anon,authenticated;

COMMIT;
