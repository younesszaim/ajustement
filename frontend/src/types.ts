/** Stable API types. Keep these aligned with FastAPI response JSON. */
export type RecordType =
  | "BASE"
  | "ADJUSTMENT_CANCEL"
  | "ADJUSTMENT_REPLACEMENT"
  | "PROXY";
export interface Context {
  /** Business snapshot date plus its exact LiMon processing/version timestamp. */
  asofdate: string;
  asofdateflow: string;
}
export interface Trade {
  rowId: string;
  tradeKey: string;
  tradeNo: string;
  foSystem: string;
  targetInstrumentType: string;
  isin: string;
  issue: string;
  valueDate: string;
  maturityDate: string;
  currency: string;
  amount: number;
  portfolio: string;
  counterparty: string;
  exposureClass: string;
  hqlaLevel: string;
  reportingLineAble: string;
  reportingLineLcr: string;
  eurAmount0d: number;
  eurAmount7d: number;
  eurAmount30d: number;
  eurAmount3m: number;
  lcrInflow: number;
  lcrOutflow: number;
  reserve: number;
  recordType: RecordType;
  isAdjusted?: boolean;
  adjustmentCount?: number;
  activeRecordType?: RecordType | "CANCELLED";
  lineageRole?: "ORIGINAL" | "REVERSAL" | "ADJUSTED";
  isActive?: boolean;
  isCancelled?: boolean;
  adjustmentBatchId?: string | null;
  lineageTimestamp?: string | null;
  [key: string]: unknown;
}
export interface FieldChange {
  field: string;
  label: string;
  oldValue: unknown;
  newValue: unknown;
}
export interface Difference {
  field: string;
  label: string;
  current: unknown;
  recalculated: unknown;
  delta?: number;
}
export interface Preview {
  /** The three-row journal shown before any durable database write. */
  operationType?: "ADJUSTMENT" | "TRADE_CANCELLATION" | "PROXY";
  original: Trade | null;
  cancellation: Trade | null;
  replacement: Trade | null;
  outputRows?: Trade[];
  changedFields: FieldChange[];
  impactedStages: string[];
  recalculatedFields: string[];
  differences: Difference[];
  rowVersion: string;
  mappingOverrides?: MappingOverride[];
}
export interface BatchPreview {
  items: Preview[];
  tradeCount: number;
  insertedRecords: number;
  impactedStages: string[];
  recalculatedFields: string[];
  aggregateDeltas: { field: string; label: string; delta: number }[];
}
export interface BatchTradeFilters {
  tradeNo?: string;
  portfolio?: string;
  counterparty?: string;
  isin?: string;
  targetInstrumentType?: string;
  currency?: string;
  exposureClass?: string;
  hqlaLevel?: string;
  reportingLineLcr?: string;
  maturityDateFrom?: string;
  maturityDateTo?: string;
  amountMin?: number | string;
  amountMax?: number | string;
}
export interface TradeLineage {
  isAdjusted: boolean;
  adjustmentCount: number;
  activeRow: Trade | null;
  rows: {
    role: "ORIGINAL" | "REVERSAL" | "ADJUSTED" | "PROXY";
    isActive: boolean;
    adjustmentBatchId: string | null;
    timestamp: string | null;
    row: Trade;
  }[];
}
export interface HistoryItem {
  adjustmentBatchId: string;
  timestamp: string;
  user: string;
  reason: string;
  baseAsOfDate: string;
  baseAsOfDateFlow: string;
  status: string;
  actionType?: "ADJUSTMENT" | "TRADE_CANCELLATION" | "PROXY" | "REVERT";
  revertedAdjustmentBatchId?: string | null;
  changedFields: FieldChange[];
  recalculatedFields: string[];
  original: Trade | null;
  cancellation: Trade | null;
  replacement: Trade | null;
  mappingOverrides?: MappingOverride[];
}

export interface MappedField {
  fieldName: string;
  mappingName: string;
  displayName: string;
  description: string;
  sourcePath: string;
  outputColumn: string;
  producerStage: string;
  downstreamStages: string[];
}
export interface MappingOverride extends MappedField {
  field: string;
  value: unknown;
  selectionType: "MANUAL_MAPPING_OVERRIDE";
}
export interface MappingRows {
  mapping: MappedField;
  items: ({ rowNumber: number } & Record<string, unknown>)[];
  page: number;
  pageSize: number;
  total: number;
}

export interface ProxyFields {
  foSystem: string;
  targetInstrumentType: string;
  isin: string;
  issue: string;
  valueDate: string;
  maturityDate: string;
  currency: string;
  amount: number;
  portfolio: string;
  counterparty: string;
}

export type Role = "reader" | "functional_admin" | "technical_admin";
export interface AuthUser {
  userId: string;
  email: string;
  displayName: string;
  roles: Role[];
  permissions: string[];
  authenticated: boolean;
  hasAccess: boolean;
}
export interface MockAuthUser extends AuthUser {
  username: string;
}
