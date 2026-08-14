import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type GridApi,
  type GridReadyEvent,
  type IGetRowsParams,
  type SelectionChangedEvent,
} from "ag-grid-community";
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Clock3,
  History,
  Loader2,
  LogOut,
  RotateCcw,
  Search,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { api } from "./api";
import { fieldLabel, fields } from "./generated/fields";
import type {
  BatchPreview,
  BatchTradeFilters,
  Context,
  HistoryItem,
  Preview,
  ProxyFields,
  Trade,
  AuthUser,
  MappedField,
} from "./types";
const money = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
ModuleRegistry.registerModules([AllCommunityModule]);
const batchGridTheme = themeQuartz.withParams({
  accentColor: "#007a4d",
  borderColor: "#e4e4e7",
  headerBackgroundColor: "#fafafa",
  headerTextColor: "#3f3f46",
  rowHoverColor: "#f4faf7",
  selectedRowBackgroundColor: "#edf7f2",
  fontFamily: "inherit",
  fontSize: 12,
  spacing: 6,
});
const fmt = (v: unknown) =>
  typeof v === "number" ? money.format(v) : String(v ?? "—");
const labels: Record<string, string> = Object.fromEntries(
  Object.entries(fields).map(([name, definition]) => [name, definition.label]),
);
const editable = [
  ["targetInstrumentType", "select"],
  ["issue", "text"],
  ["maturityDate", "date"],
  ["valueDate", "date"],
  ["amount", "number"],
  ["currency", "select"],
  ["counterparty", "text"],
  ["exposureClass", "mapping"],
  ["hqlaLevel", "mapping"],
  ["reportingLineLcr", "mapping"],
] as const;
const summary = [
  "tradeNo",
  "foSystem",
  "targetInstrumentType",
  "isin",
  "portfolio",
  "counterparty",
  "valueDate",
  "maturityDate",
  "currency",
  "amount",
  "hqlaLevel",
  "reportingLineLcr",
  "lcrOutflow",
];
export function App({
  user,
  onLogout,
}: {
  user: AuthUser;
  onLogout: () => void;
}) {
  /*
   * App orchestrates the workspace. React Query owns authoritative server
   * state; the hooks below own only drafts, selection and open dialogs. Child
   * components near the end of this file receive data/callbacks and do not
   * call the API directly.
   */
  const qc = useQueryClient();
  const canBusinessWrite = user.permissions.includes("business_write");
  const canTechnicalAdmin = user.permissions.includes("technical_admin");
  // Retry identities live in refs so rerenders cannot turn one user intention
  // into multiple backend commits. Editing the related draft clears the key.
  const singleCommitKey = useRef<string | null>(null);
  const batchCommitKey = useRef<string | null>(null);
  const revertCommitKey = useRef<string | null>(null);
  const [date, setDate] = useState(""),
    [flow, setFlow] = useState(""),
    [tradeFilter, setTradeFilter] = useState(""),
    [fo, setFo] = useState(""),
    [submitted, setSubmitted] = useState<{ trade: string; fo: string } | null>(
      null,
    ),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState(""),
    [tab, setTab] = useState("current"),
    [changes, setChanges] = useState<Record<string, unknown>>({}),
    [preview, setPreview] = useState<Preview | null>(null),
    [reason, setReason] = useState(""),
    [confirm, setConfirm] = useState(false),
    [notice, setNotice] = useState(""),
    [noticeError, setNoticeError] = useState(false),
    [step, setStep] = useState(0),
    [showGlobal, setShowGlobal] = useState(false),
    [globalDate, setGlobalDate] = useState(""),
    [globalFlow, setGlobalFlow] = useState(""),
    [batch, setBatch] = useState<
      { preview: Preview; changes: Record<string, unknown> }[]
    >([]),
    [batchReason, setBatchReason] = useState(""),
    [batchPreview, setBatchPreview] = useState<BatchPreview | null>(null),
    [showBatchPreview, setShowBatchPreview] = useState(false),
    [revertTarget, setRevertTarget] = useState<HistoryItem | null>(null),
    [revertReason, setRevertReason] = useState(""),
    [showProxy, setShowProxy] = useState(false),
    [showBatchBuilder, setShowBatchBuilder] = useState(false),
    [proxyDraftId, setProxyDraftId] = useState(() => crypto.randomUUID()),
    [proxyFields, setProxyFields] = useState<ProxyFields>({
      foSystem: "",
      targetInstrumentType: "SECURITY",
      isin: "",
      issue: "",
      valueDate: "",
      maturityDate: "",
      currency: "EUR",
      amount: 0,
      portfolio: "",
      counterparty: "",
    }),
    [proxyPreview, setProxyPreview] = useState<Preview | null>(null),
    [proxyReason, setProxyReason] = useState(""),
    [mappingTable, setMappingTable] = useState<MappedField | null>(null);
  // Query keys mirror backend scope. Context and filter changes must create a
  // new cache entry rather than display rows from an earlier LiMon version.
  const dates = useQuery({ queryKey: ["dates"], queryFn: api.dates });
  const mappedFields = useQuery({
    queryKey: ["mapped-fields"],
    queryFn: api.mappedFields,
  });
  const mappingByField = new Map(
    mappedFields.data?.map((definition) => [definition.fieldName, definition]),
  );
  useEffect(() => {
    if (!date && dates.data?.length) setDate(dates.data[0]);
  }, [dates.data, date]);
  const versions = useQuery({
    queryKey: ["versions", date],
    queryFn: () => api.versions(date),
    enabled: !!date,
  });
  useEffect(() => {
    if (versions.data?.length && !versions.data.includes(flow))
      setFlow(versions.data[0]);
  }, [versions.data, flow]);
  useEffect(() => {
    setBatch([]);
    setBatchReason("");
    setBatchPreview(null);
  }, [date, flow]);
  const ctx: Context = { asofdate: date, asofdateflow: flow };
  const canSearch = !!flow && !!submitted?.trade && !!submitted.fo;
  const trades = useQuery({
    queryKey: ["trades", ctx, submitted, page],
    queryFn: () => api.trades(ctx, submitted!.trade, submitted!.fo, page),
    enabled: canSearch,
  });
  const detail = useQuery({
    queryKey: ["trade", ctx, selected],
    queryFn: () => api.trade(ctx, selected),
    enabled: !!selected,
  });
  const lineage = useQuery({
    queryKey: ["lineage", ctx, selected],
    queryFn: () => api.lineage(ctx, selected),
    enabled: !!selected,
  });
  const history = useQuery({
    queryKey: ["history", selected],
    queryFn: () => api.history(selected),
    enabled: !!selected && tab === "history",
  });
  const globalHistory = useQuery({
    queryKey: ["global-history", globalDate, globalFlow],
    queryFn: () => api.globalHistory(globalDate, globalFlow),
    enabled: showGlobal,
  });
  const globalVersions = useQuery({
    queryKey: ["global-versions", globalDate],
    queryFn: () => api.versions(globalDate),
    enabled: showGlobal && !!globalDate,
  });
  useEffect(() => {
    if (
      batch.some((x) => x.preview.original?.rowId === selected) &&
      tab === "adjustment"
    )
      return;
    setChanges({});
    setPreview(null);
    setTab("current");
    singleCommitKey.current = null;
  }, [selected]);
  const impact = useQuery({
    queryKey: ["impact", ctx, selected, changes],
    queryFn: () => api.impact(ctx, selected, changes),
    enabled: !!selected && Object.keys(changes).length > 0,
  });
  // Preview is read-only and returns the rowVersion later submitted by commit.
  // The small delay visualizes mocked stages; production can report real work.
  const previewMut = useMutation({
    mutationFn: async () => {
      const [result] = await Promise.all([
        api.preview(ctx, selected, changes),
        new Promise((r) => setTimeout(r, 1800)),
      ]);
      return result;
    },
    onMutate: () => {
      setStep(0);
      setTab("preview");
    },
    onSuccess: (p) => {
      setPreview(p);
      setStep(4);
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  useEffect(() => {
    if (!previewMut.isPending) return;
    const id = setInterval(() => setStep((s) => Math.min(s + 1, 3)), 430);
    return () => clearInterval(id);
  }, [previewMut.isPending]);
  // This promotes either a standard preview or the internal cancellation
  // safety preview. Success invalidates all currently visible server views.
  const commit = useMutation({
    mutationFn: () =>
      preview?.operationType === "TRADE_CANCELLATION"
        ? api.commitCancellation(
            ctx,
            selected,
            reason,
            preview.rowVersion,
            (singleCommitKey.current ??= crypto.randomUUID()),
          )
        : api.commit(
            ctx,
            selected,
            changes,
            reason,
            preview!.rowVersion,
            (singleCommitKey.current ??= crypto.randomUUID()),
          ),
    onSuccess: (r) => {
      singleCommitKey.current = null;
      setConfirm(false);
      setNoticeError(false);
      setNotice(`Adjustment ${r.adjustmentBatchId} committed.`);
      setChanges({});
      setPreview(null);
      setReason("");
      qc.invalidateQueries();
      setTab("history");
    },
    onError: (e) => {
      setConfirm(false);
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  // Cancellation has no user-facing Preview tab. This internal read still
  // captures the active row and its optimistic-lock version before confirmation.
  const cancelPreviewMut = useMutation({
    mutationFn: () => api.previewCancellation(ctx, selected),
    onSuccess: (result) => {
      setPreview(result);
      setReason("");
      setConfirm(true);
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  const proxyPreviewMut = useMutation({
    mutationFn: () => api.previewProxy(ctx, proxyDraftId, proxyFields),
    onSuccess: setProxyPreview,
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  const proxyCommitMut = useMutation({
    mutationFn: () =>
      api.commitProxy(
        ctx,
        proxyDraftId,
        proxyFields,
        proxyReason,
        (singleCommitKey.current ??= crypto.randomUUID()),
      ),
    onSuccess: (result) => {
      singleCommitKey.current = null;
      setNoticeError(false);
      setNotice(`Proxy ${proxyPreview?.replacement?.tradeNo} committed as ${result.adjustmentBatchId}.`);
      setShowProxy(false);
      setProxyPreview(null);
      setProxyReason("");
      setProxyDraftId(crypto.randomUUID());
      qc.invalidateQueries();
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  // Each item carries its own preview version. The backend rejects the whole
  // batch when any one of those effective rows has become stale.
  const batchCommit = useMutation({
    mutationFn: () =>
      api.commitBatch(
        ctx,
        batch.map((x) => ({
          rowId: x.preview.original!.rowId,
          changes: x.changes,
          expectedVersion: x.preview.rowVersion,
        })),
        batchReason,
        (batchCommitKey.current ??= crypto.randomUUID()),
      ),
    onSuccess: (r) => {
      batchCommitKey.current = null;
      setNoticeError(false);
      setNotice(
        `Batch ${r.adjustmentBatchId} committed · ${r.adjustedTrades} trades · ${r.insertedRecords} rows.`,
      );
      setBatch([]);
      setBatchReason("");
      setChanges({});
      setPreview(null);
      qc.invalidateQueries();
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  const batchPreviewMut = useMutation({
    mutationFn: () =>
      api.previewBatch(
        ctx,
        batch.map((x) => ({
          rowId: x.preview.original!.rowId,
          changes: x.changes,
        })),
      ),
    onSuccess: (r) => {
      setBatchPreview(r);
      setShowBatchPreview(true);
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  // Revert creates compensating output and a linked audit batch; it never
  // deletes the selected commit or any physical output row.
  const revertMut = useMutation({
    mutationFn: () =>
      api.revertAdjustment(
        revertTarget!.adjustmentBatchId,
        {
          asofdate: revertTarget!.baseAsOfDate,
          asofdateflow: revertTarget!.baseAsOfDateFlow,
        },
        (revertTarget!.original ?? revertTarget!.replacement)!.rowId,
        revertReason,
        (revertCommitKey.current ??= crypto.randomUUID()),
      ),
    onSuccess: (r) => {
      revertCommitKey.current = null;
      setNoticeError(false);
      setNotice(
        `Adjustment reverted through audit batch ${r.adjustmentBatchId}.`,
      );
      setRevertTarget(null);
      setRevertReason("");
      qc.invalidateQueries();
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  const reconcileMut = useMutation({
    mutationFn: (item: HistoryItem) =>
      api.reconcileAdjustment(item.adjustmentBatchId),
    onSuccess: (r) => {
      setNoticeError(false);
      setNotice(
        `Adjustment reconciliation completed as batch ${r.adjustmentBatchId}.`,
      );
      qc.invalidateQueries();
    },
    onError: (e) => {
      setNoticeError(true);
      setNotice((e as Error).message);
    },
  });
  const searchGridRows = useMemo(() => {
    const items = trades.data?.items ?? [];
    const latestCancellation = new Map<string, Trade>();
    items.forEach((item) => {
      if (
        item.activeRecordType !== "CANCELLED" ||
        item.recordType !== "ADJUSTMENT_CANCEL"
      )
        return;
      const previous = latestCancellation.get(item.rowId);
      const timestamp = item.lineageTimestamp ?? String(item._createdAt ?? "");
      const previousTimestamp =
        previous?.lineageTimestamp ?? String(previous?._createdAt ?? "");
      if (!previous || timestamp >= previousTimestamp)
        latestCancellation.set(item.rowId, item);
    });
    const recordOrder: Record<string, number> = {
      BASE: 0,
      ADJUSTMENT_CANCEL: 1,
      ADJUSTMENT_REPLACEMENT: 2,
      PROXY: 2,
    };
    const batchTime = new Map<string, string>();
    items.forEach((item) => {
      if (!item.adjustmentBatchId) return;
      const key = `${item.rowId}|${item.adjustmentBatchId}`;
      const timestamp = item.lineageTimestamp ?? String(item._createdAt ?? "");
      const existing = batchTime.get(key);
      if (!existing || timestamp < existing) batchTime.set(key, timestamp);
    });
    return items
      .map((item) => ({
        ...item,
        _isLatestCancellation:
          latestCancellation.get(item.rowId)?._outputRecordId ===
          item._outputRecordId,
      }))
      .sort((left, right) => {
        // Keep every trade lineage readable by default:
        // BASE, then each batch chronologically as REVERSAL -> ADJUSTED.
        const trade = left.tradeNo.localeCompare(right.tradeNo);
        if (trade) return trade;
        const source = left.rowId.localeCompare(right.rowId);
        if (source) return source;
        const leftBase = left.recordType === "BASE" ? 0 : 1;
        const rightBase = right.recordType === "BASE" ? 0 : 1;
        if (leftBase !== rightBase) return leftBase - rightBase;
        const leftTime = left.adjustmentBatchId
          ? (batchTime.get(`${left.rowId}|${left.adjustmentBatchId}`) ?? "")
          : "";
        const rightTime = right.adjustmentBatchId
          ? (batchTime.get(`${right.rowId}|${right.adjustmentBatchId}`) ?? "")
          : "";
        const time = leftTime.localeCompare(rightTime);
        if (time) return time;
        const batch = String(left.adjustmentBatchId ?? "").localeCompare(
          String(right.adjustmentBatchId ?? ""),
        );
        if (batch) return batch;
        return (
          (recordOrder[left.recordType] ?? 99) -
          (recordOrder[right.recordType] ?? 99)
        );
      });
  }, [trades.data?.items]);
  const searchGridColumns = useMemo<ColDef<Trade>[]>(
    () => [
      { field: "tradeNo", headerName: fieldLabel("tradeNo"), pinned: "left", minWidth: 140 },
      { field: "foSystem", headerName: fieldLabel("foSystem"), minWidth: 120 },
      {
        field: "lineageRole",
        headerName: "Associated row",
        minWidth: 170,
        width: 185,
        valueGetter: ({ data }) =>
          `${data?.lineageRole ?? "ORIGINAL"}${data?.isActive ? " · ACTIVE" : ""}${data?._isLatestCancellation ? " · CANCELLED" : ""}`,
        cellRenderer: ({ data }: { data?: Trade }) => {
          if (!data) return null;
          return (
            <span className="lineage-tags">
              <span
                className={`lineage-tag role-${String(
                  data.lineageRole ?? "ORIGINAL",
                ).toLowerCase()}`}
              >
                {data.lineageRole ?? "ORIGINAL"}
              </span>
              {data.isActive && (
                <span className="lineage-tag state-active">ACTIVE</span>
              )}
              {Boolean(data._isLatestCancellation) && (
                <span className="lineage-tag state-cancelled">CANCELLED</span>
              )}
            </span>
          );
        },
      },
      { field: "recordType", headerName: fieldLabel("recordType"), minWidth: 190 },
      {
        field: "adjustmentBatchId",
        headerName: fieldLabel("adjustmentBatchId"),
        minWidth: 210,
        valueFormatter: ({ value }) => value ?? "—",
      },
      { field: "targetInstrumentType", headerName: fieldLabel("targetInstrumentType"), minWidth: 125 },
      { field: "isin", headerName: fieldLabel("isin"), minWidth: 145 },
      { field: "maturityDate", headerName: fieldLabel("maturityDate"), minWidth: 120 },
      { field: "currency", headerName: fieldLabel("currency"), width: 85 },
      {
        field: "amount",
        headerName: fieldLabel("amount"),
        filter: "agNumberColumnFilter",
        valueFormatter: ({ value }) => money.format(Number(value ?? 0)),
        minWidth: 130,
      },
      {
        field: "lcrOutflow",
        headerName: fieldLabel("lcrOutflow"),
        filter: "agNumberColumnFilter",
        valueFormatter: ({ value }) => money.format(Number(value ?? 0)),
        minWidth: 130,
      },
      { field: "hqlaLevel", headerName: fieldLabel("hqlaLevel"), width: 95 },
      { field: "reportingLineLcr", headerName: fieldLabel("reportingLineLcr"), minWidth: 125 },
    ],
    [],
  );
  const clearContext = () => {
    singleCommitKey.current = null;
    batchCommitKey.current = null;
    setSubmitted(null);
    setSelected("");
    setBatch([]);
    setBatchReason("");
    setBatchPreview(null);
    setShowBatchPreview(false);
  };
  const resetContext = () => {
    setFlow("");
    clearContext();
  };
  const search = () => {
    if (!tradeFilter.trim() || !fo) return;
    setSubmitted({ trade: tradeFilter.trim(), fo });
    setPage(1);
    setSelected("");
  };
  const change = (field: string, value: unknown) => {
    singleCommitKey.current = null;
    const original = detail.data?.[field];
    let v: unknown = value;
    if (typeof original === "number") v = value === "" ? "" : Number(value);
    setChanges((c) =>
      Object.is(original, v)
        ? Object.fromEntries(Object.entries(c).filter(([k]) => k !== field))
        : { ...c, [field]: v },
    );
    setPreview(null);
  };
  const addToBatch = () => {
    if (!preview?.original || preview.operationType === "TRADE_CANCELLATION") return;
    const original = preview.original;
    batchCommitKey.current = null;
    setBatch((items) => [
      ...items.filter(
        (x) => x.preview.original!.rowId !== original.rowId,
      ),
      { preview, changes: { ...changes } },
    ]);
    setBatchPreview(null);
    setShowBatchPreview(false);
    setNoticeError(false);
    setNotice(`${original.tradeNo} added to the adjustment batch.`);
    setSelected("");
    setSubmitted(null);
    setTradeFilter("");
    setChanges({});
    setPreview(null);
  };
  const editBatchItem = (rowId: string) => {
    const item = batch.find((x) => x.preview.original!.rowId === rowId);
    if (!item) return;
    setBatchPreview(null);
    setShowBatchPreview(false);
    setSelected(rowId);
    setChanges({ ...item.changes });
    setPreview(item.preview);
    setTab("adjustment");
  };
  return (
    <>
      <header>
        <div className="brand">
          <div className="mark">L</div>
          <div>
            <strong>LiMon</strong>
            <small>Adjustment manager</small>
          </div>
        </div>
        <div className="header-meta">
          <span className="env">DEV</span>
          <UserMenu user={user} onLogout={onLogout} />
        </div>
      </header>
      <main>
        <div className="workspace-tabs">
          <button
            className={!showGlobal ? "active" : ""}
            onClick={() => setShowGlobal(false)}
          >
            Adjustment workspace
          </button>
          <button
            className={showGlobal ? "active" : ""}
            onClick={() => setShowGlobal(true)}
          >
            Adjustment register
          </button>
        </div>
        <div className="page-title">
          <div>
            <h1>
              {showGlobal ? "Global adjustment register" : "Trade adjustments"}
            </h1>
            <p>
              {showGlobal
                ? "All committed adjustments across LiMon dates and versions."
                : "Select a LiMon snapshot, find one trade, and create an audited adjustment."}
            </p>
          </div>
          {!showGlobal && (
            <div className="page-title-actions">
              {canBusinessWrite && (
                <button
                  className="outline"
                  disabled={!flow}
                  onClick={() => setShowBatchBuilder(true)}
                >
                  Create batch adjustment
                </button>
              )}
              <button
                className="primary"
                disabled={!flow}
                onClick={() => {
                  setProxyFields((current) => ({
                    ...current,
                    valueDate: current.valueDate || date,
                    maturityDate: current.maturityDate || date,
                  }));
                  setShowProxy(true);
                }}
              >
                {canBusinessWrite ? "Add proxy trade" : "Preview proxy trade"}{" "}
                <ArrowRight />
              </button>
            </div>
          )}
        </div>
        {!showGlobal && (
          <section className="context">
            <label>
              <span>As of date</span>
              <div className="control">
                <CalendarDays />
                <input
                  type="date"
                  value={date}
                  min={dates.data?.at(-1)}
                  max={dates.data?.[0]}
                  onChange={(e) => {
                    setDate(e.target.value);
                    resetContext();
                  }}
                />
              </div>
            </label>
            <label>
              <span>Version</span>
              <div className="control">
                <Clock3 />
                <select
                  value={flow}
                  onChange={(e) => {
                    setFlow(e.target.value);
                    setSubmitted(null);
                    setSelected("");
                  }}
                  disabled={!date || versions.isLoading}
                >
                  <option value="">Select a version</option>
                  {versions.data?.map((v) => (
                    <option key={v} value={v}>
                      {new Date(v).toLocaleString("en-GB", {
                        dateStyle: "medium",
                        timeStyle: "medium",
                      })}
                    </option>
                  ))}
                </select>
              </div>
            </label>
            <div className="scope">
              <span>Snapshot scope</span>
              <strong>
                {flow
                  ? `${date} · ${new Date(flow).toLocaleTimeString("en-GB")}`
                  : "Choose a version"}
              </strong>
            </div>
          </section>
        )}
        {notice && (
          <div
            className={`notice ${noticeError ? "notice-error" : ""}`}
            role={noticeError ? "alert" : "status"}
            aria-live={noticeError ? "assertive" : "polite"}
          >
            {noticeError ? <AlertCircle /> : <ShieldCheck />}
            <span>{notice}</span>
            <button
              aria-label="Dismiss notification"
              onClick={() => {
                setNotice("");
                setNoticeError(false);
              }}
            >
              ×
            </button>
          </div>
        )}
        {!showGlobal && batch.length > 0 && (
          <section className="batch-panel">
            <div className="batch-head">
              <div>
                <span className="batch-count">{batch.length}</span>
                <div>
                  <strong>Adjustment batch</strong>
                  <small>
                    {date} · {new Date(flow).toLocaleTimeString("en-GB")} · one
                    atomic commit
                  </small>
                </div>
              </div>
              <div className="batch-head-actions">
                <button
                  className="outline"
                  disabled={batchPreviewMut.isPending}
                  onClick={() => batchPreviewMut.mutate()}
                >
                  {batchPreviewMut.isPending && <Loader2 className="spin" />}
                  Preview batch impact
                </button>
                <button
                  className="outline"
                  onClick={() => {
                    setBatch([]);
                    setBatchReason("");
                    setBatchPreview(null);
                  }}
                >
                  Clear
                </button>
              </div>
            </div>
            <div className="batch-items">
              {batch.map((x) => (
                <div key={x.preview.original!.rowId}>
                  <div>
                    <strong>{x.preview.original!.tradeNo}</strong>
                    <span>
                      {x.preview.original!.foSystem} ·{" "}
                      {x.preview.changedFields.map((c) => c.label).join(", ")}
                    </span>
                  </div>
                  <div>
                    <button
                      onClick={() => editBatchItem(x.preview.original!.rowId)}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        setBatch((items) =>
                          items.filter(
                            (i) =>
                              i.preview.original!.rowId !==
                              x.preview.original!.rowId,
                          ),
                        );
                        batchCommitKey.current = null;
                        setBatchPreview(null);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="batch-commit">
              <label>
                <span>Reason for this batch *</span>
                <textarea
                  value={batchReason}
                  onChange={(e) => {
                    batchCommitKey.current = null;
                    setBatchReason(e.target.value);
                  }}
                  placeholder="Reason applied to all adjustments in this batch…"
                />
              </label>
              <div>
                <span>
                  {batchPreview
                    ? `${batchPreview.insertedRecords} rows previewed`
                    : "Preview the combined impact before applying"}
                </span>
                <button
                  className="primary"
                  disabled={
                    !batchPreview ||
                    batchReason.trim().length < 5 ||
                    batchCommit.isPending
                  }
                  onClick={() => batchCommit.mutate()}
                >
                  {batchCommit.isPending && <Loader2 className="spin" />}Apply{" "}
                  {batch.length} adjustments
                </button>
              </div>
            </div>
          </section>
        )}
        {showBatchPreview && batchPreview && (
          <BatchPreviewDialog
            result={batchPreview}
            close={() => setShowBatchPreview(false)}
            edit={editBatchItem}
          />
        )}
        {showGlobal && (
          <section className="global-register">
            <div className="global-filters">
              <div>
                <strong>Adjustment register</strong>
                <span>
                  Choose all As Of Dates or select one date from the calendar.
                </span>
              </div>
              <div className="date-scope">
                <span>As of date scope</span>
                <div>
                  <button
                    className={!globalDate ? "active" : ""}
                    onClick={() => {
                      setGlobalDate("");
                      setGlobalFlow("");
                    }}
                  >
                    All As Of Dates
                  </button>
                  <label className={globalDate ? "active" : ""}>
                    <CalendarDays />
                    <input
                      type="date"
                      value={globalDate}
                      min={dates.data?.at(-1)}
                      max={dates.data?.[0]}
                      onChange={(e) => {
                        setGlobalDate(e.target.value);
                        setGlobalFlow("");
                      }}
                    />
                  </label>
                </div>
              </div>
              <label>
                <span>Version</span>
                <select
                  value={globalFlow}
                  onChange={(e) => setGlobalFlow(e.target.value)}
                  disabled={!globalDate}
                >
                  <option value="">
                    {globalDate ? "All versions for this date" : "All versions"}
                  </option>
                  {globalVersions.data?.map((v) => (
                    <option key={v} value={v}>
                      {new Date(v).toLocaleString("en-GB", {
                        dateStyle: "medium",
                        timeStyle: "medium",
                      })}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="global-stats">
              <span>
                <strong>
                  {globalHistory.data?.filter((x) => x.actionType !== "REVERT")
                    .filter((x) => x.status === "COMMITTED").length ?? 0}
                </strong>{" "}
                committed adjustments
              </span>
              <span>
                <strong>
                  {globalHistory.data?.filter(
                    (x) => x.status === "RECONCILIATION_REQUIRED",
                  ).length ?? 0}
                </strong>{" "}
                awaiting reconciliation
              </span>
              <span>
                <strong>
                  {globalHistory.data?.filter((x) => x.actionType === "REVERT")
                    .length ?? 0}
                </strong>{" "}
                reverted
              </span>
              <span>
                <strong>
                  {
                    new Set(globalHistory.data?.map((x) => x.baseAsOfDateFlow))
                      .size
                  }
                </strong>{" "}
                versions
              </span>
            </div>
            <div className="global-list">
              {globalHistory.isLoading ? (
                <div className="empty">
                  <Loader2 className="spin" />
                  Loading global history…
                </div>
              ) : globalHistory.data?.length ? (
                <RegisterEntries
                  items={globalHistory.data}
                  onRevert={
                    canBusinessWrite
                      ? (target) => {
                          revertCommitKey.current = null;
                          setRevertTarget(target);
                        }
                      : undefined
                  }
                  onReconcile={
                    canTechnicalAdmin
                      ? (target) => reconcileMut.mutate(target)
                      : undefined
                  }
                  reconcilingReference={
                    reconcileMut.isPending
                      ? reconcileMut.variables?.adjustmentBatchId
                      : undefined
                  }
                />
              ) : (
                <div className="blank">
                  <span>No adjustments match these filters.</span>
                </div>
              )}
            </div>
          </section>
        )}
        <section className="filter-card">
          <div className="filter-copy">
            <h2>Find a trade</h2>
            <p>Results are loaded only after both filters are provided.</p>
          </div>
          <label>
            <span>Trade / ISIN / source ID</span>
            <div className="control">
              <Search />
              <input
                value={tradeFilter}
                onChange={(e) => setTradeFilter(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder="e.g. OT-982731"
              />
            </div>
          </label>
          <label>
            <span>FO system</span>
            <select value={fo} onChange={(e) => setFo(e.target.value)}>
              <option value="">Select FO system</option>
              {["Orchestrade", "Kondor", "Murex", "SOPHIS", "APEX"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <div className="search-actions">
            {(tradeFilter || fo || submitted) && (
              <button
                className="outline"
                onClick={() => {
                  setTradeFilter("");
                  setFo("");
                  setSubmitted(null);
                  setSelected("");
                  setPage(1);
                }}
              >
                Clear search
              </button>
            )}
            <button
              className="primary"
              disabled={!flow || !tradeFilter.trim() || !fo}
              onClick={search}
            >
              Search
            </button>
          </div>
        </section>
        {!submitted ? (
          <div className="blank">
            <Search />
            <strong>No rows loaded</strong>
            <span>
              Enter a trade identifier and FO system to query Vertica.
            </span>
          </div>
        ) : (
          <section className="table-panel">
            <div className="trade-search-grid">
              <AgGridReact<Trade>
                theme={batchGridTheme}
                rowData={searchGridRows}
                columnDefs={searchGridColumns}
                defaultColDef={{
                  filter: "agTextColumnFilter",
                  floatingFilter: true,
                  sortable: true,
                  resizable: true,
                }}
                loading={trades.isLoading}
                getRowId={({ data }) =>
                  String(
                    data._outputRecordId ??
                      `${data.rowId}-${data.recordType}-${data.adjustmentBatchId ?? "base"}`,
                  )
                }
                getRowClass={({ data }) => {
                  const classes = [];
                  if (data?.rowId === selected) classes.push("trade-source-selected");
                  if (data?.isActive) classes.push("trade-row-active");
                  if (data?._isLatestCancellation)
                    classes.push("trade-row-cancelled");
                  if (data?.recordType === "ADJUSTMENT_CANCEL")
                    classes.push("trade-row-reversal");
                  return classes.join(" ");
                }}
                onRowClicked={({ data }) => data && setSelected(data.rowId)}
                overlayLoadingTemplate="Searching this snapshot…"
                overlayNoRowsTemplate="No matching trade in this version"
              />
            </div>
            <div className="pager">
              <span>{trades.data?.total ?? 0} result(s)</span>
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft />
              </button>
              <span>Page {page}</span>
              <button
                disabled={page * 10 >= (trades.data?.total ?? 0)}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight />
              </button>
            </div>
          </section>
        )}
        {selected && (tab === "adjustment" || tab === "preview") && (
          <div
            className="adjustment-overlay"
            onClick={() => setTab("current")}
          />
        )}{" "}
        {selected && (
          <section
            className={
              "details " +
              (tab === "adjustment" || tab === "preview"
                ? "adjustment-window"
                : "")
            }
          >
            <div className="detail-head">
              <div>
                <span className="eyebrow">
                  {tab === "adjustment" || tab === "preview"
                    ? "ADJUSTMENT WORKSPACE"
                    : "SELECTED TRADE"}
                </span>
                <h2>
                  {detail.data?.tradeNo}
                  <span>{detail.data?.foSystem}</span>
                </h2>
              </div>
              {detail.data &&
                (tab === "adjustment" || tab === "preview" ? (
                  <button
                    className="close-adjustment"
                    onClick={() => setTab("current")}
                  >
                    Close ×
                  </button>
                ) : (
                  <div className="selected-actions">
                    <button className="outline" onClick={() => setSelected("")}>
                      Close selected trade
                    </button>
                    {tab === "current" && (
                      detail.data.isCancelled ? (
                        <button
                          className="outline"
                          onClick={() => setTab("history")}
                        >
                          View cancellation history <History />
                        </button>
                      ) : (
                      <>
                        {canBusinessWrite && (
                          <button
                            className="cancel-trade-button"
                            disabled={cancelPreviewMut.isPending}
                            onClick={() => cancelPreviewMut.mutate()}
                          >
                            {cancelPreviewMut.isPending && (
                              <Loader2 className="spin" />
                            )}
                            Cancel trade
                          </button>
                        )}
                        <button
                          className="primary"
                          onClick={() => setTab("adjustment")}
                        >
                          {canBusinessWrite ? "Modify trade" : "Preview modification"}{" "}
                          <ArrowRight />
                        </button>
                      </>
                      )
                    )}
                  </div>
                ))}
            </div>
            <nav>
              {(tab === "adjustment" || tab === "preview"
                ? ["adjustment", "preview"]
                : ["current", "history"]
              ).map((t) => (
                <button
                  className={tab === t ? "active" : ""}
                  onClick={() => setTab(t)}
                  key={t}
                >
                  {t === "history" && <History />}
                  {t[0].toUpperCase() + t.slice(1)}
                </button>
              ))}
            </nav>
            {detail.isLoading ? (
              <div className="empty">
                <Loader2 className="spin" />
                Loading trade…
              </div>
            ) : (
              detail.data &&
              tab === "current" && (
                <div className="summary">
                  <div className="summary-lead">
                    <div>
                      <span className="record">CURRENT EFFECTIVE ROW</span>
                      {lineage.data?.isAdjusted && (
                        <span className="adjusted-flag">
                          ADJUSTED {lineage.data.adjustmentCount}×
                        </span>
                      )}
                      {detail.data.isCancelled && (
                        <span className="cancelled-flag">CANCELLED · NO ACTIVE ROW</span>
                      )}
                    </div>
                    <h3>
                      {detail.data.targetInstrumentType} ·{" "}
                      {detail.data.currency} {money.format(detail.data.amount)}
                    </h3>
                    <p>
                      {detail.data.isCancelled
                        ? "This trade was cancelled by an append-only reversal. Open History to inspect or revert the cancellation."
                        : `${detail.data.isin} · ${detail.data.portfolio} · matures ${detail.data.maturityDate}`}
                    </p>
                  </div>
                  <div className="summary-grid">
                    {summary.slice(4).map((f) => (
                      <div key={f}>
                        <span>{labels[f] ?? f.replace(/([A-Z])/g, " $1")}</span>
                        <strong>{fmt(detail.data![f])}</strong>
                      </div>
                    ))}
                  </div>
                  {lineage.data && <LineageView lineage={lineage.data} />}
                </div>
              )
            )}
            {detail.data && tab === "adjustment" && (
              <div className="adjust-grid">
                <div className="form">
                  <div className="section-title">
                    <div>
                      <h3>Adjustment inputs</h3>
                      <p>Only authorized source fields can be changed.</p>
                    </div>
                    <button
                      className="ghost"
                      onClick={() => {
                        setChanges({});
                        setPreview(null);
                      }}
                    >
                      <RotateCcw />
                      Reset
                    </button>
                  </div>
                  {editable.map(([field, type]) => {
                    const changed = field in changes;
                    return (
                      <div
                        className={"field " + (changed ? "changed" : "")}
                        key={field}
                      >
                        <label>{labels[field]}</label>
                        <div className="before">
                          <small>Original</small>
                          <span>{fmt(detail.data![field])}</span>
                        </div>
                        <ArrowRight className="arrow" />
                        <div>
                          <small>Adjusted</small>
                          {type === "mapping" && mappingByField.get(field) ? (
                            <MappingValueSelector
                              definition={mappingByField.get(field)!}
                              value={String(
                                changes[field] ?? detail.data![field] ?? "",
                              )}
                              onChange={(value) => change(field, value)}
                              viewTable={() =>
                                setMappingTable(mappingByField.get(field)!)
                              }
                            />
                          ) : type === "select" ? (
                            <select
                              value={String(
                                changes[field] ?? detail.data![field] ?? "",
                              )}
                              onChange={(e) => change(field, e.target.value)}
                            >
                              {(field === "currency"
                                ? ["EUR", "USD", "GBP", "JPY"]
                                : ["SECURITY", "LOAN", "DEPOSIT", "DERIVATIVE"]
                              ).map((x) => (
                                <option key={x}>{x}</option>
                              ))}
                            </select>
                          ) : (
                            <input
                              type={type}
                              value={String(
                                changes[field] ?? detail.data![field] ?? "",
                              )}
                              onChange={(e) => change(field, e.target.value)}
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                  <div className="form-action">
                    <button
                      className="primary"
                      disabled={
                        !Object.keys(changes).length || previewMut.isPending
                      }
                      onClick={() => previewMut.mutate()}
                    >
                      Run preview <ArrowRight />
                    </button>
                  </div>
                </div>
                <aside>
                  <h3>Impact</h3>
                  <p>The backend determines the smallest calculation path.</p>
                  <h4>Changed</h4>
                  <div className="chips">
                    {Object.keys(changes).map((k) => (
                      <span className="chip" key={k}>
                        {labels[k]}
                      </span>
                    ))}
                  </div>
                  <h4>Will recalculate</h4>
                  <ol>
                    {impact.data?.impactedStages.map((x) => (
                      <li key={x}>{x.replaceAll("_", " ")}</li>
                    ))}
                  </ol>
                </aside>
              </div>
            )}
            {tab === "preview" &&
              (previewMut.isPending ? (
                <CalculationRun
                  stages={impact.data?.impactedStages ?? []}
                  step={step}
                />
              ) : preview ? (
                <PreviewView
                  preview={preview}
                  reason={reason}
                  setReason={(value) => {
                    singleCommitKey.current = null;
                    setReason(value);
                  }}
                  apply={() => setConfirm(true)}
                  addToBatch={addToBatch}
                  inBatch={
                    !!preview.original &&
                    preview.operationType !== "TRADE_CANCELLATION" &&
                    batch.some(
                      (x) => x.preview.original!.rowId === preview.original!.rowId,
                    )
                  }
                  pending={commit.isPending}
                  canCommit={canBusinessWrite}
                />
              ) : (
                <div className="blank">
                  <span>Run a preview from the Adjustment tab.</span>
                </div>
              ))}
            {tab === "history" && (
              <div className="history">
                <div className="history-head">
                  <div>
                    <h3>Adjustment history</h3>
                    <p>
                      Committed and reverted adjustments for this trade across
                      LiMon snapshots.
                    </p>
                  </div>
                  <div className="trade-history-stats">
                    <span>
                      <strong>
                        {history.data?.filter((x) => x.actionType !== "REVERT")
                          .filter((x) => x.status === "COMMITTED").length ?? 0}
                      </strong>{" "}
                      committed
                    </span>
                    <span>
                      <strong>
                        {history.data?.filter(
                          (x) => x.status === "RECONCILIATION_REQUIRED",
                        ).length ?? 0}
                      </strong>{" "}
                      awaiting reconciliation
                    </span>
                    <span>
                      <strong>
                        {history.data?.filter((x) => x.actionType === "REVERT")
                          .length ?? 0}
                      </strong>{" "}
                      reverted
                    </span>
                  </div>
                </div>
                {history.isLoading ? (
                  <div className="empty">
                    <Loader2 className="spin" />
                    Loading history…
                  </div>
                ) : history.data?.length ? (
                  <RegisterEntries
                    items={history.data}
                    onRevert={
                      canBusinessWrite
                        ? (target) => {
                            revertCommitKey.current = null;
                            setRevertTarget(target);
                          }
                        : undefined
                    }
                    onReconcile={
                      canTechnicalAdmin
                        ? (target) => reconcileMut.mutate(target)
                        : undefined
                    }
                    reconcilingReference={
                      reconcileMut.isPending
                        ? reconcileMut.variables?.adjustmentBatchId
                        : undefined
                    }
                    showTrade={false}
                  />
                ) : (
                  <div className="blank">
                    <span>No adjustments for this trade.</span>
                  </div>
                )}
              </div>
            )}
          </section>
        )}
      </main>
      {confirm && preview && (
        <div className="modal-back">
          <div className="modal">
            <AlertCircle />
            <h2>
              {preview.operationType === "TRADE_CANCELLATION"
                ? "Cancel this trade?"
                : "Apply adjustment?"}
            </h2>
            <p>
              {preview.operationType === "TRADE_CANCELLATION"
                ? "A reversal row will cancel the active effect of "
                : "This creates one reversal and one adjusted row for "}
              <strong>{preview.original?.tradeNo}</strong>.
            </p>
            <div className="confirm-list">
              {preview.operationType !== "TRADE_CANCELLATION" && (
                <>
                  <span>Changed fields</span>
                  <strong>
                    {preview.changedFields.map((x) => x.label).join(", ")}
                  </strong>
                </>
              )}
              <span>Base snapshot</span>
              <strong>
                {date} · {new Date(flow).toLocaleTimeString("en-GB")}
              </strong>
            </div>
            {preview.operationType === "TRADE_CANCELLATION" && (
              <label className="cancel-reason">
                <span>Reason for cancellation *</span>
                <textarea
                  autoFocus
                  value={reason}
                  onChange={(event) => {
                    singleCommitKey.current = null;
                    setReason(event.target.value);
                  }}
                  placeholder="Explain why this trade must be cancelled…"
                />
              </label>
            )}
            <p className="immutable">
              Nothing is deleted. The original row and this action remain in
              the audit history and can be reverted later.
            </p>
            <div className="actions">
              <button
                onClick={() => {
                  setConfirm(false);
                  if (preview.operationType === "TRADE_CANCELLATION") {
                    setPreview(null);
                    setReason("");
                  }
                }}
              >
                {preview.operationType === "TRADE_CANCELLATION"
                  ? "Keep trade"
                  : "Cancel"}
              </button>
              <button
                className={
                  preview.operationType === "TRADE_CANCELLATION"
                    ? "cancel-trade-button"
                    : "primary"
                }
                disabled={
                  commit.isPending ||
                  (preview.operationType === "TRADE_CANCELLATION" &&
                    reason.trim().length < 5)
                }
                onClick={() => commit.mutate()}
              >
                {commit.isPending && <Loader2 className="spin" />}
                {preview.operationType === "TRADE_CANCELLATION"
                  ? "Confirm cancellation"
                  : "Apply adjustment"}
              </button>
            </div>
          </div>
        </div>
      )}
      {showProxy && (
        <ProxyDialog
          context={ctx}
          fields={proxyFields}
          setFields={(next) => {
            singleCommitKey.current = null;
            setProxyFields(next);
            setProxyPreview(null);
          }}
          preview={proxyPreview}
          reason={proxyReason}
          setReason={(value) => {
            singleCommitKey.current = null;
            setProxyReason(value);
          }}
          previewPending={proxyPreviewMut.isPending}
          commitPending={proxyCommitMut.isPending}
          canCommit={canBusinessWrite}
          runPreview={() => proxyPreviewMut.mutate()}
          commit={() => proxyCommitMut.mutate()}
          close={() => {
            setShowProxy(false);
            setProxyPreview(null);
          }}
        />
      )}
      {showBatchBuilder && (
        <BatchBuilderDialog
          context={ctx}
          close={() => setShowBatchBuilder(false)}
          complete={(result, changesByRow) => {
            setBatch(
              result.items.map((item) => ({
                preview: item,
                changes: {
                  ...(changesByRow[item.original!.rowId] ?? {}),
                },
              })),
            );
            setBatchPreview(result);
            setShowBatchPreview(true);
            setShowBatchBuilder(false);
            batchCommitKey.current = null;
          }}
        />
      )}
      {mappingTable && (
        <MappingTableDialog
          definition={mappingTable}
          close={() => setMappingTable(null)}
        />
      )}
      {revertTarget && (
        <div className="modal-back">
          <div className="modal revert-modal">
            <RotateCcw />
            <h2>Revert committed adjustment?</h2>
            <p>
              This is not a physical deletion. LiMon will append a reversal of
              the active row and a replacement restoring the state before{" "}
              <strong>{revertTarget.adjustmentBatchId}</strong>.
            </p>
            <div className="confirm-list">
              <span>Trade</span>
              <strong>
                {(revertTarget.original ?? revertTarget.replacement)?.tradeNo}
              </strong>
              <span>As of date</span>
              <strong>{revertTarget.baseAsOfDate}</strong>
              <span>Version</span>
              <strong>
                {new Date(revertTarget.baseAsOfDateFlow).toLocaleString(
                  "en-GB",
                )}
              </strong>
            </div>
            <label className="revert-reason">
              <span>Reason for reverting *</span>
              <textarea
                value={revertReason}
                onChange={(e) => {
                  revertCommitKey.current = null;
                  setRevertReason(e.target.value);
                }}
                placeholder="Explain why this committed adjustment must be reverted…"
              />
            </label>
            <p className="immutable">
              The original adjustment remains visible in the audit history.
            </p>
            <div className="actions">
              <button
                onClick={() => {
                  setRevertTarget(null);
                  setRevertReason("");
                  revertCommitKey.current = null;
                }}
              >
                Cancel
              </button>
              <button
                className="primary"
                disabled={revertReason.trim().length < 5 || revertMut.isPending}
                onClick={() => revertMut.mutate()}
              >
                {revertMut.isPending && <Loader2 className="spin" />}Revert
                adjustment
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function MappingValueSelector({
  definition,
  value,
  onChange,
  viewTable,
}: {
  definition: MappedField;
  value: string;
  onChange: (value: string) => void;
  viewTable: () => void;
}) {
  // Values load only while open. Position is calculated against the workspace
  // so mapping selectors near its bottom open upward instead of being clipped.
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [openAbove, setOpenAbove] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const values = useQuery({
    queryKey: ["mapping-values", definition.fieldName, search],
    queryFn: () => api.mappingValues(definition.fieldName, search),
    enabled: open,
  });
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div className="mapping-selector" ref={root}>
      <button
        className="mapping-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (!open && root.current) {
            const trigger = root.current.getBoundingClientRect();
            const boundary = root.current
              .closest(".details")
              ?.getBoundingClientRect();
            const boundaryTop = Math.max(boundary?.top ?? 0, 0);
            const boundaryBottom = Math.min(
              boundary?.bottom ?? window.innerHeight,
              window.innerHeight,
            );
            const spaceAbove = trigger.top - boundaryTop;
            const spaceBelow = boundaryBottom - trigger.bottom;
            setOpenAbove(spaceBelow < 360 && spaceAbove > spaceBelow);
          }
          setOpen((current) => !current);
        }}
      >
        <span>{value || "Select a mapped value"}</span>
        <ChevronsUpDown />
      </button>
      {open && (
        <div
          className={`mapping-popover ${openAbove ? "open-above" : ""}`}
        >
          <div className="mapping-search">
            <Search />
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search possible values…"
            />
          </div>
          <div className="mapping-options" role="listbox">
            {values.isLoading ? (
              <span className="mapping-empty"><Loader2 className="spin" /> Loading…</span>
            ) : values.data?.values.length ? (
              values.data.values.map((option) => (
                <button
                  role="option"
                  aria-selected={option === value}
                  key={option}
                  onClick={() => {
                    onChange(option);
                    setOpen(false);
                  }}
                >
                  <Check />
                  <span>{option}</span>
                </button>
              ))
            ) : (
              <span className="mapping-empty">No mapping value found.</span>
            )}
          </div>
          <div className="mapping-source">
            <div>
              <span>Latest mapping</span>
              <strong>{definition.mappingName}</strong>
            </div>
            <button
              onClick={() => {
                setOpen(false);
                viewTable();
              }}
            >
              <BookOpen /> View mapping table
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function MappingTableDialog({
  definition,
  close,
}: {
  definition: MappedField;
  close: () => void;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const rows = useQuery({
    queryKey: ["mapping-rows", definition.mappingName, search, page],
    queryFn: () => api.mappingRows(definition.mappingName, search, page),
  });
  const columns = Array.from(
    new Set(
      rows.data?.items.flatMap((item) =>
        Object.keys(item).filter((key) => key !== "rowNumber"),
      ) ?? [],
    ),
  );
  return (
    <div className="modal-back mapping-table-back">
      <section className="mapping-table-dialog">
        <header className="mapping-dialog-header">
          <div>
            <h2>Mapping table</h2>
            <p>{definition.description}</p>
          </div>
          <button onClick={close} aria-label="Close mapping table">×</button>
        </header>
        <div className="mapping-table-meta" aria-label="Mapping details">
          <div>
            <span>Field</span>
            <strong>{definition.displayName}</strong>
          </div>
          <div>
            <span>Mapping</span>
            <strong>{definition.mappingName}</strong>
          </div>
          <div>
            <span>Output column</span>
            <strong>{definition.outputColumn}</strong>
          </div>
          <details>
            <summary>Source</summary>
            <code title={definition.sourcePath}>{definition.sourcePath}</code>
          </details>
        </div>
        <label className="mapping-table-search">
          <Search />
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            placeholder="Filter mapping rows…"
          />
        </label>
        <div className="mapping-table-scroll">
          {rows.isLoading ? (
            <div className="empty"><Loader2 className="spin" /> Loading mapping…</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  {columns.map((column) => <th key={column}>{column}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.data?.items.map((item) => (
                  <tr key={item.rowNumber}>
                    <td>{item.rowNumber}</td>
                    {columns.map((column) => (
                      <td key={column} className={column === definition.outputColumn ? "mapping-output" : ""}>
                        {fmt(item[column])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <footer>
          <span>{rows.data?.total ?? 0} mapping row(s)</span>
          <div>
            <button disabled={page === 1} onClick={() => setPage((value) => value - 1)}>
              <ChevronLeft /> Previous
            </button>
            <span>Page {page}</span>
            <button
              disabled={page * 20 >= (rows.data?.total ?? 0)}
              onClick={() => setPage((value) => value + 1)}
            >
              Next <ChevronRight />
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

function BatchBuilderDialog({
  context,
  close,
  complete,
}: {
  context: Context;
  close: () => void;
  complete: (
    preview: BatchPreview,
    changesByRow: Record<string, Record<string, unknown>>,
  ) => void;
}) {
  const [foSystem, setFoSystem] = useState("");
  const [step, setStep] = useState<"select" | "adjust">("select");
  const [selected, setSelected] = useState<Map<string, Trade>>(new Map());
  const [changesByRow, setChangesByRow] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const gridApi = useRef<GridApi<Trade> | null>(null);
  const foSystems = useQuery({
    queryKey: ["fo-systems", context],
    queryFn: () => api.foSystems(context),
  });
  const exposureValues = useQuery({
    queryKey: ["mapping-values", "exposureClass", ""],
    queryFn: () => api.mappingValues("exposureClass"),
  });
  const hqlaValues = useQuery({
    queryKey: ["mapping-values", "hqlaLevel", ""],
    queryFn: () => api.mappingValues("hqlaLevel"),
  });
  const reportingValues = useQuery({
    queryKey: ["mapping-values", "reportingLineLcr", ""],
    queryFn: () => api.mappingValues("reportingLineLcr"),
  });
  const preview = useMutation({
    mutationFn: () =>
      api.previewBatch(
        context,
        Array.from(selected).map(([rowId]) => ({
          rowId,
          changes: changesByRow[rowId] ?? {},
        })),
      ),
    onSuccess: (result) => complete(result, changesByRow),
  });

  const columns = useMemo<ColDef<Trade>[]>(
    () => [
      { field: "tradeNo", headerName: fieldLabel("tradeNo"), pinned: "left", minWidth: 145 },
      { field: "portfolio", headerName: fieldLabel("portfolio") },
      { field: "counterparty", headerName: fieldLabel("counterparty"), minWidth: 150 },
      { field: "targetInstrumentType", headerName: fieldLabel("targetInstrumentType"), minWidth: 130 },
      { field: "isin", headerName: fieldLabel("isin"), minWidth: 140 },
      { field: "currency", headerName: fieldLabel("currency"), width: 90 },
      {
        field: "amount",
        headerName: fieldLabel("amount"),
        filter: "agNumberColumnFilter",
        valueFormatter: ({ value }) => money.format(Number(value ?? 0)),
        minWidth: 130,
      },
      {
        field: "maturityDate",
        headerName: fieldLabel("maturityDate"),
        minWidth: 125,
        filter: "agDateColumnFilter",
        filterParams: {
          comparator: (filterDate: Date, cellValue?: string) => {
            if (!cellValue) return -1;
            const cellDate = new Date(`${cellValue}T00:00:00`);
            return cellDate < filterDate ? -1 : cellDate > filterDate ? 1 : 0;
          },
        },
      },
      { field: "exposureClass", headerName: fieldLabel("exposureClass"), minWidth: 145 },
      { field: "hqlaLevel", headerName: fieldLabel("hqlaLevel"), width: 105 },
      { field: "reportingLineLcr", headerName: fieldLabel("reportingLineLcr"), minWidth: 125 },
      {
        headerName: "Status",
        valueGetter: ({ data }) =>
          data?.isAdjusted ? `Adjusted (${data.adjustmentCount})` : "Active",
        width: 120,
        filter: false,
      },
    ],
    [],
  );
  const toApiFilters = (model: Record<string, any>): BatchTradeFilters => {
    const filters: BatchTradeFilters = {};
    Object.entries(model).forEach(([field, value]) => {
      if (!value) return;
      if (field === "amount") {
        if (value.type === "greaterThan" || value.type === "greaterThanOrEqual")
          filters.amountMin = value.filter;
        else if (value.type === "lessThan" || value.type === "lessThanOrEqual")
          filters.amountMax = value.filter;
        else if (value.type === "inRange") {
          filters.amountMin = value.filter;
          filters.amountMax = value.filterTo;
        } else {
          filters.amountMin = value.filter;
          filters.amountMax = value.filter;
        }
      } else if (field === "maturityDate") {
        if (value.type === "greaterThan" || value.type === "greaterThanOrEqual")
          filters.maturityDateFrom = value.dateFrom;
        else if (value.type === "lessThan" || value.type === "lessThanOrEqual")
          filters.maturityDateTo = value.dateFrom;
        else if (value.type === "inRange") {
          filters.maturityDateFrom = value.dateFrom;
          filters.maturityDateTo = value.dateTo;
        } else {
          filters.maturityDateFrom = value.dateFrom;
          filters.maturityDateTo = value.dateFrom;
        }
      } else {
        (filters as Record<string, unknown>)[field] = value.filter ?? "";
      }
    });
    return filters;
  };
  const dataSource = useMemo(
    () => ({
      getRows: async (params: IGetRowsParams<Trade>) => {
        if (!foSystem) {
          params.successCallback([], 0);
          return;
        }
        const pageSize = params.endRow - params.startRow;
        const page = Math.floor(params.startRow / pageSize) + 1;
        try {
          const result = await api.batchTrades(
            context,
            foSystem,
            toApiFilters(params.filterModel),
            page,
            pageSize,
          );
          params.successCallback(result.items, result.total);
        } catch {
          params.failCallback();
        }
      },
    }),
    [context.asofdate, context.asofdateflow, foSystem],
  );
  useEffect(() => {
    if (gridApi.current) gridApi.current.setGridOption("datasource", dataSource);
  }, [dataSource]);
  const selectionChanged = (event: SelectionChangedEvent<Trade>) => {
    setSelected((current) => {
      const next = new Map(current);
      event.api.forEachNode((node) => {
        if (!node.data) return;
        if (node.isSelected()) next.set(node.data.rowId, node.data);
        else next.delete(node.data.rowId);
      });
      return next;
    });
  };
  const updateChange = (rowId: string, field: string, value: string) =>
    setChangesByRow((current) => {
      const row = { ...(current[rowId] ?? {}) };
      const typedValue = field === "amount" ? Number(value) : value;
      const original = selected.get(rowId)?.[field];
      if (value === "" || Object.is(original, typedValue)) delete row[field];
      else row[field] = typedValue;
      return { ...current, [rowId]: row };
    });
  const everyTradeReady =
    selected.size > 0 &&
    Array.from(selected.keys()).every(
      (rowId) => Object.keys(changesByRow[rowId] ?? {}).length > 0,
    );
  return (
    <div className="modal-back batch-builder-back">
      <section className="batch-builder-dialog">
        <header>
          <div>
            <span className="eyebrow">BATCH ADJUSTMENT</span>
            <h2>{step === "select" ? "Select trades" : "Adjust selected trades"}</h2>
            <p>{context.asofdate} · {new Date(context.asofdateflow).toLocaleString("en-GB")}</p>
          </div>
          <button onClick={close}>Close ×</button>
        </header>
        {step === "select" ? (
          <>
            <div className="batch-ag-toolbar">
              <label><span>FO system *</span><select value={foSystem} onChange={(event) => {
                setFoSystem(event.target.value);
                setSelected(new Map());
              }}><option value="">Select an FO system</option>{foSystems.data?.map((system) => <option key={system}>{system}</option>)}</select></label>
              <div><strong>{selected.size}</strong><span>selected</span></div>
              <button onClick={() => { setSelected(new Map()); gridApi.current?.deselectAll(); }} disabled={!selected.size}>Clear selection</button>
            </div>
            <p className="batch-grid-help">Filter directly below any column header, then select the active trades to adjust.</p>
            <div className="batch-ag-grid">
              <AgGridReact<Trade>
                theme={batchGridTheme}
                columnDefs={columns}
                defaultColDef={{ filter: "agTextColumnFilter", floatingFilter: true, sortable: false, resizable: true }}
                rowModelType="infinite"
                datasource={dataSource}
                cacheBlockSize={50}
                maxBlocksInCache={5}
                pagination
                paginationPageSize={50}
                paginationPageSizeSelector={false}
                rowSelection={{ mode: "multiRow", checkboxes: true, headerCheckbox: false, enableClickSelection: true }}
                selectionColumnDef={{ pinned: "left", width: 48, sortable: false }}
                getRowId={({ data }) => data.rowId}
                onGridReady={(event: GridReadyEvent<Trade>) => { gridApi.current = event.api; }}
                onSelectionChanged={selectionChanged}
                overlayNoRowsTemplate={foSystem ? "No active trade matches these filters" : "Select an FO system"}
              />
            </div>
          </>
        ) : (
          <div className="batch-adjust-workspace">
            <div className="batch-adjust-intro"><strong>{selected.size} selected trades</strong><span>Set at least one change for every trade. Each editor uses the same original → adjusted layout as the single-trade workspace.</span></div>
            {Array.from(selected.values()).map((trade, index) => {
              const changes = changesByRow[trade.rowId] ?? {};
              const fields: Array<[string, string, string, string[]?]> = [
                ["amount", "Amount", "number"],
                ["currency", "Currency", "select", ["EUR", "USD", "GBP", "JPY"]],
                ["maturityDate", "Maturity date", "date"],
                ["exposureClass", "Exposure class", "select", exposureValues.data?.values ?? []],
                ["hqlaLevel", "HQLA", "select", hqlaValues.data?.values ?? []],
                ["reportingLineLcr", "Reporting line LCR", "select", reportingValues.data?.values ?? []],
              ];
              return <article className="batch-trade-editor" key={trade.rowId}>
                <header><div><span>TRADE {index + 1}</span><strong>{trade.tradeNo}</strong><small>{trade.portfolio} · {trade.counterparty}</small></div><button onClick={() => setSelected((current) => { const next = new Map(current); next.delete(trade.rowId); return next; })}>Remove</button></header>
                <div className="batch-editor-fields">{fields.map(([field, label, type, options]) => <div className={field in changes ? "changed" : ""} key={field}>
                  <label>{label}</label><span><small>Original</small><strong>{fmt(trade[field])}</strong></span><ArrowRight /><span><small>Adjusted</small>{type === "select" ? <select value={String(changes[field] ?? "")} onChange={(e) => updateChange(trade.rowId, field, e.target.value)}><option value="">Unchanged</option>{options?.map((option) => <option key={option}>{option}</option>)}</select> : <input type={type} value={String(changes[field] ?? "")} placeholder={String(trade[field] ?? "")} onChange={(e) => updateChange(trade.rowId, field, e.target.value)} />}</span>
                </div>)}</div>
              </article>;
            })}
          </div>
        )}
        {preview.error && <div className="batch-builder-error">{(preview.error as Error).message}</div>}
        <footer>
          <span>{step === "select" ? "Only active rows are selectable." : "Each trade is version-checked and the final commit remains atomic."}</span>
          <div className="batch-builder-footer-actions">
            {step === "adjust" && <button onClick={() => setStep("select")}>Back to selection</button>}
            {step === "select" ? <button className="primary" disabled={!selected.size} onClick={() => setStep("adjust")}>Adjust {selected.size} trades <ArrowRight /></button> : <button className="primary" disabled={!everyTradeReady || preview.isPending} onClick={() => preview.mutate()}>{preview.isPending && <Loader2 className="spin" />} Preview {selected.size} adjustments</button>}
          </div>
        </footer>
      </section>
    </div>
  );
}

function UserMenu({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const initials = user.displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  const permissionLabels: Record<string, string> = {
    read: "Read trades and history",
    preview: "Run adjustment previews",
    business_write: "Commit and revert adjustments",
    technical_admin: "Technical health and reconciliation",
  };

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        className="user-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="user-avatar">{initials || <UserRound />}</span>
        <span className="user-trigger-copy">
          <strong>{user.displayName}</strong>
          <small>{user.roles.join(", ").replaceAll("_", " ")}</small>
        </span>
        <ChevronDown />
      </button>
      {open && (
        <section className="user-popover" role="dialog" aria-label="User details">
          <div className="user-popover-head">
            <span className="user-avatar large">{initials || <UserRound />}</span>
            <div>
              <strong>{user.displayName}</strong>
              <span>{user.email}</span>
            </div>
          </div>
          <div className="user-detail">
            <span>User ID</span>
            <code>{user.userId}</code>
          </div>
          <div className="user-detail">
            <span>Application role</span>
            <strong>{user.roles.join(", ").replaceAll("_", " ")}</strong>
          </div>
          <div className="user-permissions">
            <span>Permissions</span>
            <ul>
              {user.permissions.map((permission) => (
                <li key={permission}>
                  <Check /> {permissionLabels[permission] ?? permission}
                </li>
              ))}
            </ul>
          </div>
          <button className="user-signout" onClick={onLogout}>
            <LogOut /> Sign out
          </button>
        </section>
      )}
    </div>
  );
}
function ProxyDialog({
  context,
  fields,
  setFields,
  preview,
  reason,
  setReason,
  previewPending,
  commitPending,
  canCommit,
  runPreview,
  commit,
  close,
}: {
  context: Context;
  fields: ProxyFields;
  setFields: (fields: ProxyFields) => void;
  preview: Preview | null;
  reason: string;
  setReason: (value: string) => void;
  previewPending: boolean;
  commitPending: boolean;
  canCommit: boolean;
  runPreview: () => void;
  commit: () => void;
  close: () => void;
}) {
  const required =
    fields.foSystem &&
    fields.portfolio &&
    fields.counterparty &&
    fields.valueDate &&
    fields.maturityDate &&
    fields.amount !== 0;
  const update = (field: keyof ProxyFields, value: string) =>
    setFields({
      ...fields,
      [field]: field === "amount" ? Number(value) : value,
    });
  return (
    <div className="modal-back proxy-back">
      <section className="proxy-dialog">
        <header>
          <div>
            <span className="eyebrow">NEW ADJUSTMENT TYPE</span>
            <h2>Add proxy trade</h2>
            <p>
              {context.asofdate} ·{" "}
              {new Date(context.asofdateflow).toLocaleString("en-GB")}
            </p>
          </div>
          <button onClick={close}>Close ×</button>
        </header>
        <div className="proxy-fields">
          {(
            [
              ["foSystem", "FO system", "text"],
              ["portfolio", "Portfolio", "text"],
              ["counterparty", "Counterparty", "text"],
              ["isin", "ISIN", "text"],
              ["issue", "Issue", "text"],
              ["valueDate", "Value date", "date"],
              ["maturityDate", "Maturity date", "date"],
              ["amount", "Amount", "number"],
            ] as const
          ).map(([field, label, type]) => (
            <label key={field}>
              <span>{label}</span>
              <input
                type={type}
                value={fields[field]}
                onChange={(event) => update(field, event.target.value)}
              />
            </label>
          ))}
          <label>
            <span>Instrument type</span>
            <select
              value={fields.targetInstrumentType}
              onChange={(event) =>
                update("targetInstrumentType", event.target.value)
              }
            >
              {['SECURITY', 'LOAN', 'DEPOSIT', 'DERIVATIVE'].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Currency</span>
            <select
              value={fields.currency}
              onChange={(event) => update("currency", event.target.value)}
            >
              {['EUR', 'USD', 'GBP', 'JPY'].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        </div>
        {!preview ? (
          <div className="proxy-actions">
            <span>The trade number and output record ID are generated automatically.</span>
            <button
              className="primary"
              disabled={!required || previewPending}
              onClick={runPreview}
            >
              {previewPending && <Loader2 className="spin" />} Preview proxy
            </button>
          </div>
        ) : (
          <div className="proxy-preview">
            <div className="generated-id">
              <span>Generated trade number</span>
              <strong>{preview.replacement?.tradeNo}</strong>
            </div>
            {preview.replacement && (
              <RowCard title="Proxy output row" row={preview.replacement} tone="adjusted" />
            )}
            {canCommit && (
              <label>
                <span>Reason *</span>
                <textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Explain why this proxy is required…"
                />
              </label>
            )}
            <div className="proxy-actions">
              <button onClick={() => setFields({ ...fields })}>Modify</button>
              {canCommit && (
                <button
                  className="primary"
                  disabled={reason.trim().length < 5 || commitPending}
                  onClick={commit}
                >
                  {commitPending && <Loader2 className="spin" />} Commit proxy
                </button>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
function LineageView({ lineage }: { lineage: import("./types").TradeLineage }) {
  return (
    <section className="lineage">
      <div className="lineage-head">
        <div>
          <h3>Associated rows</h3>
          <p>
            {lineage.isAdjusted
              ? "Original row plus all reversal and adjusted rows."
              : "This trade has not been adjusted."}
          </p>
        </div>
        <span>{lineage.rows.length} row(s)</span>
      </div>
      <div className="lineage-table">
        <div className="lineage-row headings">
          <span>State</span>
          <span>Record type</span>
          <span>Batch</span>
          <span>Amount</span>
          <span>LCR outflow</span>
          <span>Created</span>
        </div>
        {lineage.rows.map((x, i) => (
          <div
            className={"lineage-row " + (x.isActive ? "active" : "")}
            key={`${x.role}-${x.adjustmentBatchId ?? "base"}-${i}`}
          >
            <span>
              <i />
              {x.role}
              {x.isActive && <b>ACTIVE</b>}
            </span>
            <code>{x.row.recordType}</code>
            <span>{x.adjustmentBatchId ?? "—"}</span>
            <strong>{money.format(x.row.amount)}</strong>
            <span>{money.format(x.row.lcrOutflow)}</span>
            <time>
              {x.timestamp
                ? new Date(x.timestamp).toLocaleString("en-GB")
                : "Production row"}
            </time>
          </div>
        ))}
      </div>
      <p className="lineage-note">
        <ShieldCheck />
        The active row is the latest adjusted replacement. Original and reversal
        rows remain immutable for audit.
      </p>
    </section>
  );
}
function CalculationRun({ stages, step }: { stages: string[]; step: number }) {
  const phases = [
    "Read authoritative row",
    "Resolve impacted calculations",
    "Run LiMon calculation stages",
    "Build reversal and adjusted rows",
  ];
  return (
    <div className="calculation">
      <Loader2 className="spin hero-loader" />
      <h3>Calculating preview</h3>
      <p>Nothing is written to Vertica during preview.</p>
      <div>
        {phases.map((x, i) => (
          <div
            className={i < step ? "done" : i === step ? "running" : ""}
            key={x}
          >
            <span>
              {i < step ? (
                <Check />
              ) : i === step ? (
                <Loader2 className="spin" />
              ) : (
                i + 1
              )}
            </span>
            <div>
              <strong>{x}</strong>
              {i === 2 && stages.length > 0 && (
                <small>
                  {stages.map((s) => s.replaceAll("_", " ")).join(" → ")}
                </small>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
function RowCard({
  title,
  row,
  tone,
}: {
  title: string;
  row: Trade;
  tone: string;
}) {
  const fields = [
    "amount",
    "maturityDate",
    "eurAmount30d",
    "eurAmount3m",
    "reportingLineLcr",
    "lcrOutflow",
  ];
  return (
    <article className={"row-card " + tone}>
      <header>
        <span>{title}</span>
        <code>{row.recordType}</code>
      </header>
      {fields.map((f) => (
        <div key={f}>
          <span>{labels[f] ?? f}</span>
          <strong>{fmt(row[f])}</strong>
        </div>
      ))}
    </article>
  );
}
const historyTrade = (item: HistoryItem) =>
  item.original ?? item.replacement ?? item.cancellation!;

function RegisterEntries({
  items,
  onRevert,
  onReconcile,
  reconcilingReference,
  showTrade = true,
}: {
  items: HistoryItem[];
  onRevert?: (item: HistoryItem) => void;
  onReconcile?: (item: HistoryItem) => void;
  reconcilingReference?: string;
  showTrade?: boolean;
}) {
  const reverts = new Map(
    items
      .filter((x) => x.actionType === "REVERT" && x.revertedAdjustmentBatchId)
      .map((x) => [
        `${historyTrade(x).rowId}:${x.revertedAdjustmentBatchId}`,
        x,
      ]),
  );
  const commits = items.filter((x) => x.actionType !== "REVERT");
  return (
    <>
      {commits.map((commit) => {
        const trade = historyTrade(commit);
        const revert = reverts.get(
          `${trade.rowId}:${commit.adjustmentBatchId}`,
        );
        const display = revert ? { ...commit, status: "REVERTED" } : commit;
        return (
          <div
            className={
              "register-pair " + (revert ? "is-reverted" : "is-committed")
            }
            key={`${commit.adjustmentBatchId}-${trade.rowId}`}
          >
            <HistoryEntry
              item={display}
              showTrade={showTrade}
              onRevert={
                revert || commit.status !== "COMMITTED" || !onRevert
                  ? undefined
                  : onRevert
              }
              onReconcile={
                commit.status === "RECONCILIATION_REQUIRED" && onReconcile
                  ? onReconcile
                  : undefined
              }
              reconciling={
                reconcilingReference === commit.adjustmentBatchId
              }
            />
            {revert && (
              <div className="linked-revert">
                <div className="link-line">
                  <span>↳</span>
                  <strong>Reverted by {revert.adjustmentBatchId}</strong>
                  <time>
                    {new Date(revert.timestamp).toLocaleString("en-GB", {
                      dateStyle: "medium",
                      timeStyle: "medium",
                    })}
                  </time>
                </div>
                <div className="linked-revert-meta">
                  <span>
                    By <strong>{revert.user}</strong>
                  </span>
                  <span>
                    Reason: <strong>{revert.reason}</strong>
                  </span>
                </div>
                <div className="restore-changes">
                  {revert.changedFields.map((x) => (
                    <span key={x.field}>
                      {x.label}: {fmt(x.oldValue)} →{" "}
                      <strong>{fmt(x.newValue)}</strong>
                    </span>
                  ))}
                </div>
                <small>
                  The commit remains in the audit trail; its business effect was
                  neutralized by a new reversal and replacement.
                </small>
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}
function HistoryEntry({
  item: h,
  showTrade = false,
  onRevert,
  onReconcile,
  reconciling = false,
}: {
  item: HistoryItem;
  showTrade?: boolean;
  onRevert?: (item: HistoryItem) => void;
  onReconcile?: (item: HistoryItem) => void;
  reconciling?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const trade = historyTrade(h);
  return (
    <article
      className={
        "history-entry " + (h.actionType === "REVERT" ? "revert-entry" : "")
      }
    >
      <div className="history-line">
        <span className="timeline-dot" />
        <div className="history-main">
          <div className="history-title">
            <div>
              <strong>
                {showTrade
                  ? `${trade.tradeNo} · ${h.adjustmentBatchId}`
                  : h.adjustmentBatchId}
              </strong>
              <span className="badge">
                {h.actionType === "TRADE_CANCELLATION"
                  ? "TRADE CANCELLATION"
                  : h.actionType === "PROXY"
                    ? "PROXY"
                    : h.actionType === "REVERT"
                      ? "REVERT"
                      : h.status}
              </span>
              {h.actionType !== "ADJUSTMENT" &&
                h.actionType !== "REVERT" && (
                  <span className="badge">{h.status}</span>
                )}
            </div>
            <time>
              {new Date(h.timestamp).toLocaleString("en-GB", {
                dateStyle: "medium",
                timeStyle: "medium",
              })}
            </time>
          </div>
          {h.revertedAdjustmentBatchId && (
            <div className="revert-link">
              Reverts adjustment <strong>{h.revertedAdjustmentBatchId}</strong>
            </div>
          )}
          <div className="audit-meta">
            <div>
              <span>Changed by</span>
              <strong>{h.user}</strong>
            </div>
            <div>
              <span>As of date</span>
              <strong>{h.baseAsOfDate}</strong>
            </div>
            <div>
              <span>Version</span>
              <strong>
                {new Date(h.baseAsOfDateFlow).toLocaleString("en-GB", {
                  dateStyle: "medium",
                  timeStyle: "medium",
                })}
              </strong>
            </div>
          </div>
          <blockquote>{h.reason}</blockquote>
          {!!h.mappingOverrides?.length && (
            <div className="history-mapping-overrides">
              {h.mappingOverrides.map((override) => (
                <span key={override.field}>
                  Manual mapping override · {override.displayName}:{" "}
                  <strong>{fmt(override.value)}</strong>
                </span>
              ))}
            </div>
          )}
          <div className="history-changes">
            {h.changedFields.map((c) => (
              <div key={c.field}>
                <span>{c.label}</span>
                <code>{fmt(c.oldValue)}</code>
                <ArrowRight />
                <strong>{fmt(c.newValue)}</strong>
              </div>
            ))}
          </div>
          <div className="history-actions">
            <button
              className="detail-toggle"
              onClick={() => setOpen((x) => !x)}
            >
              {open
                ? "Hide adjustment rows"
                : "View original, reversal and adjusted rows"}
              <ArrowRight />
            </button>
            {onRevert && h.actionType !== "REVERT" && h.status === "COMMITTED" && (
              <button className="revert-button" onClick={() => onRevert(h)}>
                Revert adjustment
              </button>
            )}
            {onReconcile && h.status === "RECONCILIATION_REQUIRED" && (
              <button
                className="reconcile-button"
                disabled={reconciling}
                onClick={() => onReconcile(h)}
              >
                {reconciling ? (
                  <>
                    <Loader2 className="spin" /> Reconciling…
                  </>
                ) : (
                  <>
                    <RotateCcw /> Retry reconciliation
                  </>
                )}
              </button>
            )}
          </div>
          {open && (
            <>
              <div className="history-row-flow">
                {h.original && (
                  <RowCard title="Original" row={h.original} tone="original" />
                )}
                {h.cancellation && (
                  <RowCard title="Reversal" row={h.cancellation} tone="reversal" />
                )}
                {h.replacement && (
                  <RowCard
                    title={h.actionType === "PROXY" ? "Proxy" : "Adjusted"}
                    row={h.replacement}
                    tone="adjusted"
                  />
                )}
              </div>
              <div className="recalculated">
                <span>Recalculated fields</span>
                <div>
                  {h.recalculatedFields.map((x) => (
                    <span className="chip" key={x}>
                      {labels[x] ?? x}
                    </span>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
function BatchPreviewDialog({
  result,
  close,
  edit,
}: {
  result: BatchPreview;
  close: () => void;
  edit: (id: string) => void;
}) {
  return (
    <div className="batch-preview-back">
      <section className="batch-preview-dialog">
        <header>
          <div>
            <span className="eyebrow">AUTHORITATIVE BATCH PREVIEW</span>
            <h2>Combined adjustment impact</h2>
            <p>
              {result.tradeCount} trades · {result.insertedRecords} journal rows
              · no database changes
            </p>
          </div>
          <button onClick={close}>×</button>
        </header>
        <div className="batch-impact">
          <div>
            <span>Impacted stages</span>
            <div>
              {result.impactedStages.map((x) => (
                <span className="chip" key={x}>
                  {x.replaceAll("_", " ")}
                </span>
              ))}
            </div>
          </div>
          <div>
            <span>Combined quantitative deltas</span>
            <div>
              {result.aggregateDeltas.length ? (
                result.aggregateDeltas.map((x) => (
                  <strong key={x.field}>
                    {x.label}: {x.delta > 0 ? "+" : ""}
                    {money.format(x.delta)}
                  </strong>
                ))
              ) : (
                <strong>No additive delta</strong>
              )}
            </div>
          </div>
        </div>
        <div className="batch-preview-items">
          {result.items.map((item) => (
            <article key={item.original!.rowId}>
              <div className="batch-preview-title">
                <div>
                  <strong>{item.original!.tradeNo}</strong>
                  <span>
                    {item.original!.foSystem} ·{" "}
                    {item.changedFields.map((x) => x.label).join(", ")}
                  </span>
                </div>
                <button
                  className="outline"
                  onClick={() => edit(item.original!.rowId)}
                >
                  Edit adjustment
                </button>
              </div>
              <div className="batch-mini-flow">
                <RowCard title="Original" row={item.original!} tone="original" />
                <RowCard
                  title="Reversal"
                  row={item.cancellation!}
                  tone="reversal"
                />
                <RowCard
                  title="Adjusted"
                  row={item.replacement!}
                  tone="adjusted"
                />
              </div>
            </article>
          ))}
        </div>
        <footer>
          <span>
            <ShieldCheck />
            Preview recalculated from authoritative rows
          </span>
          <button className="primary" onClick={close}>
            Return to batch
          </button>
        </footer>
      </section>
    </div>
  );
}
function PreviewView({
  preview,
  reason,
  setReason,
  apply,
  addToBatch,
  inBatch,
  pending,
  canCommit,
}: {
  preview: Preview;
  reason: string;
  setReason: (x: string) => void;
  apply: () => void;
  addToBatch: () => void;
  inBatch: boolean;
  pending: boolean;
  canCommit: boolean;
}) {
  // Mirror backend concepts: output journal, calculated differences, ordered
  // stages and manual mapping decisions. No write occurs from this component.
  return (
    <div className="preview">
      <div className="preview-head">
        <div>
          <span className="eyebrow">SERVER PREVIEW COMPLETE</span>
          <h3>What will be recorded</h3>
        </div>
        <span className="safe">
          <ShieldCheck />
          No database changes yet
        </span>
      </div>
      <div className="row-flow">
        {preview.original && (
          <RowCard title="Original" row={preview.original} tone="original" />
        )}
        {preview.cancellation && (
          <>
            <ArrowRight />
            <RowCard title="Reversal" row={preview.cancellation} tone="reversal" />
          </>
        )}
        {preview.replacement && (
          <>
            <ArrowRight />
            <RowCard title="Adjusted" row={preview.replacement} tone="adjusted" />
          </>
        )}
      </div>
      <section className="calculation-result">
        <div className="result-heading">
          <div>
            <span className="eyebrow">CALCULATION RESULT</span>
            <h3>Values after recalculation</h3>
          </div>
          <strong>{preview.differences.length} value changes</strong>
        </div>

        {preview.differences.length ? (
          <div className="result-table">
            <div className="result-table-head">
              <span>Field</span>
              <span>Before</span>
              <span>After preview</span>
              <span>Difference</span>
            </div>
            {preview.differences.map((difference) => {
              const override = preview.mappingOverrides?.find(
                (item) => item.field === difference.field,
              );
              return (
                <div className="result-row" key={difference.field}>
                  <span className="result-field">
                    <strong>{difference.label}</strong>
                    {override && <small>Manual mapping selection</small>}
                  </span>
                  <span className="result-before">{fmt(difference.current)}</span>
                  <strong className="result-after">
                    {fmt(difference.recalculated)}
                  </strong>
                  <span className="result-delta">
                    {typeof difference.delta === "number"
                      ? `${difference.delta > 0 ? "+" : ""}${money.format(
                          difference.delta,
                        )}`
                      : "Changed"}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="result-empty">
            <Check />
            <div>
              <strong>No value recalculation is required</strong>
              <span>
                {preview.operationType === "TRADE_CANCELLATION"
                  ? "The preview only creates a reversal of the active row."
                  : "The generated row keeps the values shown above."}
              </span>
            </div>
          </div>
        )}

        <div className="calculation-path">
          <span>Calculation path</span>
          <div>
            {preview.impactedStages.length ? (
              preview.impactedStages.map((stage, index) => (
                <span key={stage}>
                  <b>{index + 1}</b>
                  {stage.replaceAll("_", " ")}
                </span>
              ))
            ) : (
              <span className="no-stage">No calculation stage executed</span>
            )}
          </div>
        </div>

        {!!preview.mappingOverrides?.length && (
          <div className="mapping-decisions">
            <div className="mapping-decisions-title">
              <strong>Selected mapping values</strong>
              <span>Manual values used in this preview</span>
            </div>
            <div className="mapping-decision-head">
              <span>Field</span>
              <span>Selected value</span>
              <span>Recalculated afterwards</span>
            </div>
            {preview.mappingOverrides.map((override) => (
              <div className="mapping-decision-row" key={override.field}>
                <strong>{override.displayName}</strong>
                <span>{fmt(override.value)}</span>
                <span>
                  {override.downstreamStages
                    .map((stage) => stage.replaceAll("_", " "))
                    .join(" → ") || "No downstream stage"}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
      {canCommit && (
        <section className="reason">
          <label>Reason for single adjustment *</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Required only when applying this trade immediately…"
          />
          <small>
            For a multi-trade batch, the shared reason is entered in the batch
            panel.
          </small>
        </section>
      )}
      <div className="apply-row">
        <span>
          <ShieldCheck />
          Original row remains immutable
        </span>
        <div className="preview-actions">
          {canCommit && preview.operationType !== "TRADE_CANCELLATION" && (
            <button className="outline" onClick={addToBatch}>
              {inBatch ? "Update batch" : "Add to batch"}
            </button>
          )}
          {canCommit && (
            <button
              className="primary"
              onClick={apply}
              disabled={reason.trim().length < 5 || pending}
            >
              {preview.operationType === "TRADE_CANCELLATION"
                ? "Cancel trade effect"
                : "Apply this adjustment"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
