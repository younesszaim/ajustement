export type RecordType =
  | "BASE"
  | "ADJUSTMENT_CANCEL"
  | "ADJUSTMENT_REPLACEMENT"
  | "PROXY";
export interface Context {
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
  activeRecordType?: RecordType;
  lineageRole?: "ORIGINAL" | "REVERSAL" | "ADJUSTED";
  isActive?: boolean;
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
}
export interface BatchPreview {
  items: Preview[];
  tradeCount: number;
  insertedRecords: number;
  impactedStages: string[];
  recalculatedFields: string[];
  aggregateDeltas: { field: string; label: string; delta: number }[];
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
