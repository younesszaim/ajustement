-- Rich development population for AG Grid filtering and multi-trade adjustment.
-- These rows belong only to the Vertica simulator and are safe to reapply.
BEGIN;

INSERT INTO vertica_sim.output_completude_table(
    output_record_id,asofdate,asofdateflow,trade_no,fo_system,isin,portfolio,
    counterparty,target_instrument_type,issue,maturity_date,value_date,currency,
    amount,eur_amount_0d,eur_amount_7d,eur_amount_30d,eur_amount_3m,lcr_inflow,
    lcr_outflow,reserve_amount,exposure_class,hqla_level,reporting_line_lcr,
    record_type
)
SELECT
    'SIM-BATCH-' || lpad(n::text,3,'0'),
    DATE '2026-08-06',
    TIMESTAMP '2026-08-07 11:14:09',
    CASE
      WHEN n <= 30 THEN 'OT-BATCH-' || (1000+n)
      ELSE 'MX-BATCH-' || (1000+n)
    END,
    CASE WHEN n <= 30 THEN 'Orchestrade' ELSE 'Murex' END,
    'FRBATCH' || lpad(n::text,5,'0'),
    (ARRAY['LIQUIDITY','TREASURY','COLLATERAL'])[1 + (n % 3)],
    (ARRAY['CP_BANK_01','CP_BANK_02','CP_SOV_01','CP_CORP_01','CP_CENTRAL_BANK'])[1 + (n % 5)],
    (ARRAY['SECURITY','LOAN','DEPOSIT'])[1 + (n % 3)],
    'BATCH_TEST_ISSUER_' || lpad(n::text,2,'0'),
    DATE '2026-08-06' + (5 + n * 3),
    DATE '2026-08-06',
    (ARRAY['EUR','USD','GBP'])[1 + (n % 3)],
    100000 + n * 75000,
    CASE WHEN n % 3 = 0 THEN (100000 + n * 75000) * 0.92 ELSE 100000 + n * 75000 END,
    CASE WHEN 5 + n * 3 <= 7 THEN 100000 + n * 75000 ELSE 0 END,
    CASE WHEN 5 + n * 3 BETWEEN 8 AND 30 THEN 100000 + n * 75000 ELSE 0 END,
    CASE WHEN 5 + n * 3 > 30 THEN 100000 + n * 75000 ELSE 0 END,
    0,
    (100000 + n * 75000) * 0.20,
    0,
    (ARRAY['FINANCIAL','SOVEREIGN','CORPORATE','CENTRAL_BANK','RETAIL'])[1 + (n % 5)],
    (ARRAY['L1','L2A','L2B','NON_HQLA'])[1 + (n % 4)],
    (ARRAY['RL_SEC_01','RL_SEC_03','RL_LOAN_01','RL_DEP_01'])[1 + (n % 4)],
    'BASE'
FROM generate_series(1,40) AS seed(n)
ON CONFLICT(output_record_id) DO NOTHING;

COMMIT;
