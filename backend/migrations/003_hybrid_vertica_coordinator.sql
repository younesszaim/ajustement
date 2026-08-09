BEGIN;

-- Mutable operational coordinator. Immutable audit remains in adjustment_batches.
CREATE TABLE IF NOT EXISTS public.adjustment_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES public.adjustment_projects(project_id),
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
    vertica_record_ids text[] NOT NULL DEFAULT '{}',
    error_code text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT adjustment_requests_idempotency_uk UNIQUE(project_id,idempotency_key),
    CONSTRAINT adjustment_requests_reference_uk UNIQUE(project_id,batch_reference),
    CONSTRAINT adjustment_requests_action CHECK(action_type IN ('ADJUSTMENT','REVERT')),
    CONSTRAINT adjustment_requests_status CHECK(status IN ('PENDING','VERTICA_COMMITTED','COMMITTED','FAILED','RECONCILIATION_REQUIRED')),
    CONSTRAINT adjustment_requests_reason CHECK(length(btrim(reason))>=5),
    CONSTRAINT adjustment_requests_items CHECK(item_count>0)
);

-- Hybrid audit snapshots do not reference the Supabase output demo table.
-- External record identifiers point to immutable rows in Vertica.
CREATE TABLE IF NOT EXISTS public.adjustment_item_snapshots (
    snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    adjustment_batch_id uuid NOT NULL REFERENCES public.adjustment_batches(adjustment_batch_id),
    source_row_id text NOT NULL,
    trade_key text NOT NULL,
    trade_no text,
    fo_system text NOT NULL,
    expected_row_version text NOT NULL,
    vertica_original_record_id text NOT NULL,
    vertica_cancellation_record_id text NOT NULL,
    vertica_replacement_record_id text NOT NULL,
    original_snapshot jsonb NOT NULL,
    cancellation_snapshot jsonb NOT NULL,
    replacement_snapshot jsonb NOT NULL,
    changed_fields jsonb NOT NULL DEFAULT '[]',
    recalculated_fields jsonb NOT NULL DEFAULT '[]',
    impacted_stages jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT adjustment_item_snapshots_trade_uk UNIQUE(adjustment_batch_id,source_row_id)
);

CREATE INDEX IF NOT EXISTS adjustment_requests_recovery_idx ON public.adjustment_requests(status,updated_at);
CREATE INDEX IF NOT EXISTS adjustment_snapshots_trade_idx ON public.adjustment_item_snapshots(source_row_id,created_at DESC);
ALTER TABLE public.adjustment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adjustment_item_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.adjustment_requests,public.adjustment_item_snapshots FROM anon,authenticated;

COMMIT;
