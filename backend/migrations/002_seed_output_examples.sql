BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS out_completude_base_source_uk
ON public.out_completude_ldp_bmf(project_id,asofdate,asofdateflow,source_row_id)
WHERE record_type='BASE';

WITH project AS (
  SELECT project_id FROM public.adjustment_projects WHERE project_key='limon_ldp_bmf'
), examples(asofdate,asofdateflow,source_row_id,trade_no,fo_system,trade_key,payload,amount,currency,lcr_inflow,lcr_outflow,reserve_amount) AS (
 VALUES
  ('2026-08-06'::date,'2026-08-07 04:45:02'::timestamp,'LDP-BMF-0001','OT-982731','Orchestrade','Orchestrade|OT-982731|FR0012345678',
   '{"targetInstrumentType":"SECURITY","isin":"FR0012345678","issue":"ISSUER_A","valueDate":"2026-08-06","maturityDate":"2026-08-20","portfolio":"LIQUIDITY","counterparty":"CP_BANK_01","exposureClass":"FINANCIAL","hqlaLevel":"L1","reportingLineAble":"ABLE_01","reportingLineLcr":"RL_SEC_01","eurAmount0d":0,"eurAmount7d":0,"eurAmount30d":1000000,"eurAmount3m":0}'::jsonb,1000000::numeric,'EUR',0::numeric,200000::numeric,0::numeric),
  ('2026-08-06','2026-08-07 04:45:02','LDP-BMF-0002','MX-441082','Murex','Murex|MX-441082|DE000A1EWWW0',
   '{"targetInstrumentType":"SECURITY","isin":"DE000A1EWWW0","issue":"ISSUER_B","valueDate":"2026-08-06","maturityDate":"2026-09-18","portfolio":"TREASURY","counterparty":"CP_BANK_02","exposureClass":"FINANCIAL","hqlaLevel":"L1","reportingLineAble":"ABLE_02","reportingLineLcr":"RL_SEC_03","eurAmount0d":0,"eurAmount7d":0,"eurAmount30d":0,"eurAmount3m":750000}'::jsonb,750000,'EUR',0,150000,0),
  ('2026-08-06','2026-08-07 11:14:09','LDP-BMF-0003','KD-109221','Kondor','Kondor|KD-109221|GB00B03MLX29',
   '{"targetInstrumentType":"DEPOSIT","isin":"GB00B03MLX29","issue":"ISSUER_C","valueDate":"2026-08-06","maturityDate":"2026-08-13","portfolio":"LIQUIDITY","counterparty":"CP_BANK_03","exposureClass":"INSTITUTION","hqlaLevel":"NON_HQLA","reportingLineAble":"ABLE_04","reportingLineLcr":"RL_DEP_01","eurAmount0d":0,"eurAmount7d":2400000,"eurAmount30d":0,"eurAmount3m":0}'::jsonb,2400000,'EUR',0,480000,0),
  ('2026-08-05','2026-08-06 06:12:00','LDP-BMF-0004','SP-830114','SOPHIS','SOPHIS|SP-830114|US0378331005',
   '{"targetInstrumentType":"SECURITY","isin":"US0378331005","issue":"ISSUER_D","valueDate":"2026-08-05","maturityDate":"2026-08-25","portfolio":"MARKET","counterparty":"CP_CORP_01","exposureClass":"CORPORATE","hqlaLevel":"L2B","reportingLineAble":"ABLE_06","reportingLineLcr":"RL_SEC_02","eurAmount0d":0,"eurAmount7d":0,"eurAmount30d":320000,"eurAmount3m":0}'::jsonb,320000,'EUR',0,64000,0),
  ('2026-08-05','2026-08-06 06:12:00','LDP-BMF-0005','AP-230912','APEX','APEX|AP-230912|FR0000120271',
   '{"targetInstrumentType":"LOAN","isin":"FR0000120271","issue":"ISSUER_E","valueDate":"2026-08-05","maturityDate":"2026-11-05","portfolio":"BANKING","counterparty":"CP_CORP_02","exposureClass":"CORPORATE","hqlaLevel":"NON_HQLA","reportingLineAble":"ABLE_08","reportingLineLcr":"RL_LOAN_03","eurAmount0d":0,"eurAmount7d":0,"eurAmount30d":0,"eurAmount3m":5000000}'::jsonb,5000000,'EUR',0,1000000,0)
)
INSERT INTO public.out_completude_ldp_bmf(project_id,asofdate,asofdateflow,source_row_id,trade_key,trade_no,fo_system,record_type,row_version,row_payload,amount,currency,lcr_inflow,lcr_outflow,reserve_amount,created_by)
SELECT p.project_id,e.asofdate,e.asofdateflow,e.source_row_id,e.trade_key,e.trade_no,e.fo_system,'BASE',
       encode(digest(e.payload::text,'sha256'),'hex'),e.payload,e.amount,e.currency,e.lcr_inflow,e.lcr_outflow,e.reserve_amount,'database-seed'
FROM project p CROSS JOIN examples e
WHERE NOT EXISTS (
  SELECT 1 FROM public.out_completude_ldp_bmf o WHERE o.project_id=p.project_id AND o.asofdate=e.asofdate
  AND o.asofdateflow=e.asofdateflow AND o.source_row_id=e.source_row_id AND o.record_type='BASE'
);

COMMIT;
