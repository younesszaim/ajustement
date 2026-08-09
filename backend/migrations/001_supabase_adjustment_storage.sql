BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.adjustment_projects (
    project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_key text NOT NULL UNIQUE,
    display_name text NOT NULL,
    output_table_name text NOT NULL,
    editable_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    additive_measure_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    calculation_stages jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL,
    CONSTRAINT adjustment_projects_key_format CHECK (project_key ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT adjustment_projects_output_format CHECK (output_table_name ~ '^[a-z][a-z0-9_]*$')
);

CREATE TABLE IF NOT EXISTS public.adjustment_batches (
    adjustment_batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES public.adjustment_projects(project_id),
    batch_reference text NOT NULL,
    action_type text NOT NULL DEFAULT 'ADJUSTMENT',
    status text NOT NULL DEFAULT 'COMMITTED',
    base_asofdate date NOT NULL,
    base_asofdateflow timestamp without time zone NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    reverted_adjustment_batch_id uuid REFERENCES public.adjustment_batches(adjustment_batch_id),
    idempotency_key text NOT NULL,
    trade_count integer NOT NULL DEFAULT 1,
    inserted_record_count integer NOT NULL DEFAULT 2,
    request_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT adjustment_batches_action CHECK (action_type IN ('ADJUSTMENT','REVERT')),
    CONSTRAINT adjustment_batches_status CHECK (status IN ('COMMITTED','FAILED')),
    CONSTRAINT adjustment_batches_reason CHECK (length(btrim(reason)) >= 5),
    CONSTRAINT adjustment_batches_counts CHECK (trade_count > 0 AND inserted_record_count = trade_count * 2),
    CONSTRAINT adjustment_batches_project_reference_uk UNIQUE (project_id,batch_reference),
    CONSTRAINT adjustment_batches_project_idempotency_uk UNIQUE (project_id,idempotency_key),
    CONSTRAINT adjustment_batches_revert_link CHECK (
        (action_type = 'REVERT' AND reverted_adjustment_batch_id IS NOT NULL)
        OR (action_type = 'ADJUSTMENT' AND reverted_adjustment_batch_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS public.out_completude_ldp_bmf (
    output_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES public.adjustment_projects(project_id),
    asofdate date NOT NULL,
    asofdateflow timestamp without time zone NOT NULL,
    source_row_id text NOT NULL,
    trade_key text NOT NULL,
    trade_no text,
    fo_system text NOT NULL,
    record_type text NOT NULL DEFAULT 'BASE',
    lineage_sequence bigint GENERATED ALWAYS AS IDENTITY,
    adjustment_batch_id uuid REFERENCES public.adjustment_batches(adjustment_batch_id),
    parent_record_id uuid REFERENCES public.out_completude_ldp_bmf(output_record_id),
    original_record_id uuid REFERENCES public.out_completude_ldp_bmf(output_record_id),
    row_version text NOT NULL,
    row_payload jsonb NOT NULL,
    amount numeric(38,10),
    currency text,
    lcr_inflow numeric(38,10),
    lcr_outflow numeric(38,10),
    reserve_amount numeric(38,10),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    CONSTRAINT out_completude_record_type CHECK (record_type IN ('BASE','ADJUSTMENT_CANCEL','ADJUSTMENT_REPLACEMENT')),
    CONSTRAINT out_completude_payload_object CHECK (jsonb_typeof(row_payload) = 'object'),
    CONSTRAINT out_completude_adjustment_link CHECK (
        (record_type = 'BASE' AND adjustment_batch_id IS NULL)
        OR (record_type <> 'BASE' AND adjustment_batch_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS public.adjustment_batch_items (
    adjustment_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    adjustment_batch_id uuid NOT NULL REFERENCES public.adjustment_batches(adjustment_batch_id),
    source_row_id text NOT NULL,
    trade_key text NOT NULL,
    trade_no text,
    fo_system text NOT NULL,
    expected_row_version text NOT NULL,
    original_record_id uuid NOT NULL REFERENCES public.out_completude_ldp_bmf(output_record_id),
    cancellation_record_id uuid NOT NULL REFERENCES public.out_completude_ldp_bmf(output_record_id),
    replacement_record_id uuid NOT NULL REFERENCES public.out_completude_ldp_bmf(output_record_id),
    changed_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    recalculated_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    impacted_stages jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT adjustment_batch_items_trade_uk UNIQUE (adjustment_batch_id,source_row_id)
);

CREATE TABLE IF NOT EXISTS public.adjustment_field_changes (
    field_change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adjustment_item_id uuid NOT NULL REFERENCES public.adjustment_batch_items(adjustment_item_id),
    field_name text NOT NULL,
    old_value jsonb,
    new_value jsonb,
    value_type text NOT NULL,
    is_recalculated boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT adjustment_field_changes_item_field_uk UNIQUE (adjustment_item_id,field_name)
);

CREATE TABLE IF NOT EXISTS public.adjustment_action_events (
    action_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id uuid NOT NULL REFERENCES public.adjustment_projects(project_id),
    adjustment_batch_id uuid REFERENCES public.adjustment_batches(adjustment_batch_id),
    source_row_id text,
    event_type text NOT NULL,
    event_status text NOT NULL DEFAULT 'SUCCESS',
    actor_user_id text NOT NULL,
    actor_role text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    asofdate date,
    asofdateflow timestamp without time zone,
    correlation_id text,
    client_ip inet,
    user_agent text,
    event_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT adjustment_action_events_status CHECK (event_status IN ('SUCCESS','FAILED','DENIED')),
    CONSTRAINT adjustment_action_events_type CHECK (event_type IN (
        'DATE_SELECTED','VERSION_SELECTED','TRADE_SEARCHED','TRADE_VIEWED',
        'ADJUSTMENT_STARTED','FIELD_CHANGED','PREVIEW_REQUESTED','PREVIEW_COMPLETED',
        'BATCH_ITEM_ADDED','BATCH_ITEM_REMOVED','BATCH_COMMITTED',
        'ADJUSTMENT_COMMITTED','REVERT_REQUESTED','ADJUSTMENT_REVERTED','ERROR'
    ))
);

CREATE INDEX IF NOT EXISTS out_completude_context_trade_idx ON public.out_completude_ldp_bmf(asofdate,asofdateflow,fo_system,trade_no);
CREATE INDEX IF NOT EXISTS out_completude_source_lineage_idx ON public.out_completude_ldp_bmf(project_id,asofdate,asofdateflow,source_row_id,lineage_sequence);
CREATE INDEX IF NOT EXISTS out_completude_batch_idx ON public.out_completude_ldp_bmf(adjustment_batch_id);
CREATE INDEX IF NOT EXISTS adjustment_batches_context_idx ON public.adjustment_batches(project_id,base_asofdate,base_asofdateflow,created_at DESC);
CREATE INDEX IF NOT EXISTS adjustment_batches_revert_idx ON public.adjustment_batches(reverted_adjustment_batch_id) WHERE reverted_adjustment_batch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS adjustment_events_project_time_idx ON public.adjustment_action_events(project_id,occurred_at DESC);
CREATE INDEX IF NOT EXISTS adjustment_events_actor_time_idx ON public.adjustment_action_events(actor_user_id,occurred_at DESC);

CREATE OR REPLACE VIEW public.v_out_completude_ldp_bmf_current AS
SELECT DISTINCT ON (project_id,asofdate,asofdateflow,source_row_id)
    output_record_id,project_id,asofdate,asofdateflow,source_row_id,trade_key,trade_no,
    fo_system,record_type,adjustment_batch_id,parent_record_id,original_record_id,
    row_version,row_payload,amount,currency,lcr_inflow,lcr_outflow,reserve_amount,
    created_at,created_by,lineage_sequence
FROM public.out_completude_ldp_bmf
WHERE record_type IN ('BASE','ADJUSTMENT_REPLACEMENT')
ORDER BY project_id,asofdate,asofdateflow,source_row_id,lineage_sequence DESC;

CREATE OR REPLACE VIEW public.v_adjustment_register AS
SELECT b.adjustment_batch_id,b.batch_reference,b.action_type,b.status,b.base_asofdate,
       b.base_asofdateflow,b.reason,b.created_at,b.created_by,b.trade_count,
       b.inserted_record_count,b.reverted_adjustment_batch_id,p.project_key,p.display_name,
       EXISTS (SELECT 1 FROM public.adjustment_batches r WHERE r.reverted_adjustment_batch_id=b.adjustment_batch_id AND r.status='COMMITTED') AS is_reverted
FROM public.adjustment_batches b
JOIN public.adjustment_projects p USING (project_id);

CREATE OR REPLACE FUNCTION public.prevent_adjustment_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; % is not allowed',TG_TABLE_NAME,TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS out_completude_append_only ON public.out_completude_ldp_bmf;
CREATE TRIGGER out_completude_append_only BEFORE UPDATE OR DELETE ON public.out_completude_ldp_bmf FOR EACH ROW EXECUTE FUNCTION public.prevent_adjustment_mutation();
DROP TRIGGER IF EXISTS adjustment_batches_append_only ON public.adjustment_batches;
CREATE TRIGGER adjustment_batches_append_only BEFORE UPDATE OR DELETE ON public.adjustment_batches FOR EACH ROW EXECUTE FUNCTION public.prevent_adjustment_mutation();
DROP TRIGGER IF EXISTS adjustment_items_append_only ON public.adjustment_batch_items;
CREATE TRIGGER adjustment_items_append_only BEFORE UPDATE OR DELETE ON public.adjustment_batch_items FOR EACH ROW EXECUTE FUNCTION public.prevent_adjustment_mutation();
DROP TRIGGER IF EXISTS adjustment_changes_append_only ON public.adjustment_field_changes;
CREATE TRIGGER adjustment_changes_append_only BEFORE UPDATE OR DELETE ON public.adjustment_field_changes FOR EACH ROW EXECUTE FUNCTION public.prevent_adjustment_mutation();
DROP TRIGGER IF EXISTS adjustment_events_append_only ON public.adjustment_action_events;
CREATE TRIGGER adjustment_events_append_only BEFORE UPDATE OR DELETE ON public.adjustment_action_events FOR EACH ROW EXECUTE FUNCTION public.prevent_adjustment_mutation();

INSERT INTO public.adjustment_projects(project_key,display_name,output_table_name,editable_fields,additive_measure_fields,calculation_stages,created_by,updated_by)
VALUES (
    'limon_ldp_bmf','LiMon LDP BMF Adjustments','out_completude_ldp_bmf',
    '["targetInstrumentType","issue","maturityDate","valueDate","amount","currency","counterparty","securityId"]'::jsonb,
    '["amount","eurAmount0d","eurAmount7d","eurAmount30d","eurAmount3m","lcrInflow","lcrOutflow","reserve"]'::jsonb,
    '["instrument_classification","issuer_enrichment","counterparty_enrichment","exposure_class","hqla","reporting_lines","eur_amount","buckets","lcr_impacts"]'::jsonb,
    'schema-bootstrap','schema-bootstrap'
)
ON CONFLICT (project_key) DO NOTHING;

-- Supabase exposes the public schema through PostgREST. These tables are backend-only.
ALTER TABLE public.adjustment_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adjustment_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.out_completude_ldp_bmf ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adjustment_batch_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adjustment_field_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adjustment_action_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.adjustment_projects,public.adjustment_batches,public.out_completude_ldp_bmf,
    public.adjustment_batch_items,public.adjustment_field_changes,public.adjustment_action_events FROM anon,authenticated;
REVOKE ALL ON public.v_out_completude_ldp_bmf_current,public.v_adjustment_register FROM anon,authenticated;

COMMIT;
