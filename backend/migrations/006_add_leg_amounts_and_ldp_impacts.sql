-- Add the real LiMon Cash/Titre adjustment inputs and additive LDP outputs.
-- Existing SECURITY fixtures initialise the Titre leg; LOAN/DEPOSIT fixtures
-- initialise the Cash leg so both selection contexts are testable.

ALTER TABLE vertica_sim.output_completude_table
    ADD COLUMN IF NOT EXISTS security_leg_flag smallint,
    ADD COLUMN IF NOT EXISTS cash_amount_eur numeric(38,10),
    ADD COLUMN IF NOT EXISTS security_amount_eur numeric(38,10),
    ADD COLUMN IF NOT EXISTS ldp_impact_asset numeric(38,10),
    ADD COLUMN IF NOT EXISTS ldp_impact_asset_cash_gestion numeric(38,10),
    ADD COLUMN IF NOT EXISTS ldp_impact_inflow numeric(38,10),
    ADD COLUMN IF NOT EXISTS ldp_impact_outflow numeric(38,10),
    ADD COLUMN IF NOT EXISTS ldp_impact_lcr_reglementaire numeric(38,10),
    ADD COLUMN IF NOT EXISTS ldp_impact_lcr_gestion numeric(38,10);

ALTER TABLE vertica_sim.output_completude_table
    DISABLE TRIGGER output_sim_append_only;

UPDATE vertica_sim.output_completude_table
SET security_leg_flag = CASE WHEN target_instrument_type = 'SECURITY' THEN 1 ELSE 0 END,
    cash_amount_eur = CASE WHEN target_instrument_type = 'SECURITY' THEN 0 ELSE amount END,
    security_amount_eur = CASE WHEN target_instrument_type = 'SECURITY' THEN amount ELSE 0 END,
    ldp_impact_asset = CASE WHEN target_instrument_type = 'SECURITY' THEN amount ELSE 0 END,
    ldp_impact_asset_cash_gestion = CASE WHEN target_instrument_type = 'SECURITY' THEN 0 ELSE amount END,
    ldp_impact_inflow = lcr_inflow,
    ldp_impact_outflow = lcr_outflow,
    ldp_impact_lcr_reglementaire = amount + COALESCE(lcr_inflow, 0) - COALESCE(lcr_outflow, 0),
    ldp_impact_lcr_gestion = amount + COALESCE(lcr_inflow, 0) - COALESCE(lcr_outflow, 0)
WHERE security_leg_flag IS NULL;

ALTER TABLE vertica_sim.output_completude_table
    ENABLE TRIGGER output_sim_append_only;

ALTER TABLE vertica_sim.output_completude_table
    ALTER COLUMN security_leg_flag SET NOT NULL,
    ALTER COLUMN cash_amount_eur SET NOT NULL,
    ALTER COLUMN security_amount_eur SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'output_sim_security_leg_flag_check'
          AND conrelid = 'vertica_sim.output_completude_table'::regclass
    ) THEN
        ALTER TABLE vertica_sim.output_completude_table
            ADD CONSTRAINT output_sim_security_leg_flag_check
            CHECK (security_leg_flag IN (0, 1));
    END IF;
END;
$$;
