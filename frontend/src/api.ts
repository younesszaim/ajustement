import type {
  BatchPreview,
  Context,
  HistoryItem,
  Preview,
  Trade,
  TradeLineage,
} from "./types";
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
  versions: (d: string) => json<string[]>(`/api/versions?asofdate=${d}`),
  trades: (c: Context, q: string, fo: string, page: number) =>
    json<{ items: Trade[]; total: number }>(
      `/api/trades?asofdate=${c.asofdate}&asofdateflow=${encodeURIComponent(c.asofdateflow)}&search=${encodeURIComponent(q)}&foSystem=${encodeURIComponent(fo)}&page=${page}&pageSize=10`,
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
  commit: (
    c: Context,
    id: string,
    changes: Record<string, unknown>,
    reason: string,
    rowVersion: string,
    key: string,
  ) =>
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
