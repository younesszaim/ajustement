import type {
  BatchPreview,
  BatchTradeFilters,
  Context,
  HistoryItem,
  Preview,
  ProxyFields,
  Trade,
  TradeLineage,
  ControlledFieldOption,
} from "./types";

/**
 * Single browser-to-backend boundary.
 *
 * Components call these typed functions instead of using fetch directly. The
 * FastAPI's `detail` message is converted to an Error so React Query mutations
 * can display it consistently.
 *
 * Example: `api.trade(context, rowId)` always supplies both snapshot keys.
 */
const json = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(url, init);
  const body = await r.json().catch(() => ({ detail: r.statusText }));
  if (!r.ok) throw new Error(body.detail ?? "Request failed");
  return body;
};
const post = <T>(url: string, body: unknown) =>
  json<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const api = {
  dates: () => json<string[]>("/api/asofdates"),
  // Snapshot-scoped reads. Query keys in App.tsx must contain the same context.
  versions: (d: string) => json<string[]>(`/api/versions?asofdate=${d}`),
  foSystems: (c: Context) =>
    json<string[]>(
      `/api/fo-systems?asofdate=${encodeURIComponent(c.asofdate)}&asofdateflow=${encodeURIComponent(c.asofdateflow)}`,
    ),
  batchTrades: (
    c: Context,
    foSystem: string,
    filters: BatchTradeFilters,
    page: number,
    pageSize = 50,
  ) =>
    post<{ items: Trade[]; total: number }>("/api/trades/batch-search", {
      context: c,
      foSystem,
      filters,
      page,
      pageSize,
    }),
  trades: (c: Context, q: string, fo: string, leg: 0 | 1, page: number) =>
    json<{ items: Trade[]; total: number }>(
      `/api/trades?asofdate=${c.asofdate}&asofdateflow=${encodeURIComponent(c.asofdateflow)}&search=${encodeURIComponent(q)}&foSystem=${encodeURIComponent(fo)}&securityLegFlag=${leg}&page=${page}&pageSize=10`,
    ),
  trade: (c: Context, id: string) =>
    json<Trade>(
      `/api/trades/${id}?asofdate=${c.asofdate}&asofdateflow=${encodeURIComponent(c.asofdateflow)}`,
    ),
  history: (id: string) => json<HistoryItem[]>(`/api/trades/${id}/history`),
  lineage: (c: Context, id: string) =>
    json<TradeLineage>(
      `/api/trades/${id}/lineage?asofdate=${c.asofdate}&asofdateflow=${encodeURIComponent(c.asofdateflow)}`,
    ),
  globalHistory: (asofdate: string, asofdateflow: string) =>
    json<HistoryItem[]>(
      `/api/adjustments/history?asofdate=${encodeURIComponent(asofdate)}&asofdateflow=${encodeURIComponent(asofdateflow)}`,
    ),
  adjustmentOptions: () =>
    json<ControlledFieldOption[]>("/api/adjustment-options"),
  reconcileAdjustment: (batchReference: string) =>
    post<{
      adjustmentBatchId: string;
      status: string;
      insertedRecords: number;
      adjustedTrades: number;
    }>(`/api/adjustments/${encodeURIComponent(batchReference)}/reconcile`, {}),
  impact: (c: Context, id: string, changes: Record<string, unknown>) =>
    post<{ impactedStages: string[] }>("/api/adjustments/impact", {
      context: c,
      rowId: id,
      changes,
    }),
  preview: (c: Context, id: string, changes: Record<string, unknown>) =>
    post<Preview>("/api/adjustments/preview", {
      context: c,
      rowId: id,
      changes,
    }),
  previewCancellation: (c: Context, id: string) =>
    post<Preview>("/api/adjustments/cancel/preview", {
      context: c,
      rowId: id,
    }),
  commitCancellation: (
    c: Context,
    id: string,
    reason: string,
    rowVersion: string,
    key: string,
  ) =>
    post<{
      adjustmentBatchId: string;
      status: string;
      insertedRecords: number;
    }>("/api/adjustments/cancel/commit", {
      context: c,
      rowId: id,
      reason,
      expectedVersion: rowVersion,
      idempotencyKey: key,
    }),
  previewProxy: (c: Context, draftId: string, fields: ProxyFields) =>
    post<Preview>("/api/adjustments/proxy/preview", {
      context: c,
      draftId,
      fields,
    }),
  commitProxy: (
    c: Context,
    draftId: string,
    fields: ProxyFields,
    reason: string,
    key: string,
  ) =>
    post<{
      adjustmentBatchId: string;
      status: string;
      insertedRecords: number;
    }>("/api/adjustments/proxy/commit", {
      context: c,
      draftId,
      fields,
      reason,
      idempotencyKey: key,
    }),
  commit: (
    c: Context,
    id: string,
    changes: Record<string, unknown>,
    reason: string,
    rowVersion: string,
    key: string,
  ) =>
    // expectedVersion protects against stale previews; key protects retries.
    post<{
      adjustmentBatchId: string;
      status: string;
      insertedRecords: number;
    }>("/api/adjustments/commit", {
      context: c,
      rowId: id,
      changes,
      reason,
      expectedVersion: rowVersion,
      idempotencyKey: key,
    }),
  commitBatch: (
    c: Context,
    items: {
      rowId: string;
      changes: Record<string, unknown>;
      expectedVersion: string;
    }[],
    reason: string,
    key: string,
  ) =>
    post<{
      adjustmentBatchId: string;
      status: string;
      insertedRecords: number;
      adjustedTrades: number;
    }>("/api/adjustments/batch/commit", {
      context: c,
      items,
      reason,
      idempotencyKey: key,
    }),
  previewBatch: (
    c: Context,
    items: { rowId: string; changes: Record<string, unknown> }[],
  ) =>
    post<BatchPreview>("/api/adjustments/batch/preview", { context: c, items }),
  revertAdjustment: (
    batchId: string,
    c: Context,
    rowId: string,
    reason: string,
    key: string,
  ) =>
    post<{
      adjustmentBatchId: string;
      status: string;
      insertedRecords: number;
    }>(`/api/adjustments/${encodeURIComponent(batchId)}/revert`, {
      context: c,
      rowId,
      reason,
      idempotencyKey: key,
    }),
};
