import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  History,
  Loader2,
  RotateCcw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api } from "./api";
import type {
  BatchPreview,
  Context,
  HistoryItem,
  Preview,
  Trade,
} from "./types";
const money = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const fmt = (v: unknown) =>
  typeof v === "number" ? money.format(v) : String(v ?? "—");
const labels: Record<string, string> = {
  targetInstrumentType: "Instrument type",
  issue: "Issue",
  maturityDate: "Maturity date",
  valueDate: "Value date",
  amount: "Amount",
  currency: "Currency",
  counterparty: "Counterparty",
  securityId: "Security ID",
  reportingLineLcr: "Reporting line LCR",
  eurAmount30d: "EUR amount 30D",
  eurAmount3m: "EUR amount 3M",
  lcrOutflow: "LCR outflow",
  hqlaLevel: "HQLA",
};
const editable = [
  ["targetInstrumentType", "select"],
  ["issue", "text"],
  ["maturityDate", "date"],
  ["valueDate", "date"],
  ["amount", "number"],
  ["currency", "select"],
  ["counterparty", "text"],
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
const col = createColumnHelper<Trade>();
export function App() {
  const qc = useQueryClient();
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
    [revertReason, setRevertReason] = useState("");
  const dates = useQuery({ queryKey: ["dates"], queryFn: api.dates });
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
      batch.some((x) => x.preview.original.rowId === selected) &&
      tab === "adjustment"
    )
      return;
    setChanges({});
    setPreview(null);
    setTab("current");
  }, [selected]);
  const impact = useQuery({
    queryKey: ["impact", ctx, selected, changes],
    queryFn: () => api.impact(ctx, selected, changes),
    enabled: !!selected && Object.keys(changes).length > 0,
  });
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
    onError: (e) => setNotice((e as Error).message),
  });
  useEffect(() => {
    if (!previewMut.isPending) return;
    const id = setInterval(() => setStep((s) => Math.min(s + 1, 3)), 430);
    return () => clearInterval(id);
  }, [previewMut.isPending]);
  const commit = useMutation({
    mutationFn: () =>
      api.commit(
        ctx,
        selected,
        changes,
        reason,
        preview!.rowVersion,
        crypto.randomUUID(),
      ),
    onSuccess: (r) => {
      setConfirm(false);
      setNotice(`Adjustment ${r.adjustmentBatchId} committed.`);
      setChanges({});
      setPreview(null);
      setReason("");
      qc.invalidateQueries();
      setTab("history");
    },
    onError: (e) => {
      setConfirm(false);
      setNotice((e as Error).message);
    },
  });
  const batchCommit = useMutation({
    mutationFn: () =>
      api.commitBatch(
        ctx,
        batch.map((x) => ({
          rowId: x.preview.original.rowId,
          changes: x.changes,
          expectedVersion: x.preview.rowVersion,
        })),
        batchReason,
        crypto.randomUUID(),
      ),
    onSuccess: (r) => {
      setNotice(
        `Batch ${r.adjustmentBatchId} committed · ${r.adjustedTrades} trades · ${r.insertedRecords} rows.`,
      );
      setBatch([]);
      setBatchReason("");
      setChanges({});
      setPreview(null);
      qc.invalidateQueries();
    },
    onError: (e) => setNotice((e as Error).message),
  });
  const batchPreviewMut = useMutation({
    mutationFn: () =>
      api.previewBatch(
        ctx,
        batch.map((x) => ({
          rowId: x.preview.original.rowId,
          changes: x.changes,
        })),
      ),
    onSuccess: (r) => {
      setBatchPreview(r);
      setShowBatchPreview(true);
    },
    onError: (e) => setNotice((e as Error).message),
  });
  const revertMut = useMutation({
    mutationFn: () =>
      api.revertAdjustment(
        revertTarget!.adjustmentBatchId,
        {
          asofdate: revertTarget!.baseAsOfDate,
          asofdateflow: revertTarget!.baseAsOfDateFlow,
        },
        revertTarget!.original.rowId,
        revertReason,
        crypto.randomUUID(),
      ),
    onSuccess: (r) => {
      setNotice(
        `Adjustment reverted through audit batch ${r.adjustmentBatchId}.`,
      );
      setRevertTarget(null);
      setRevertReason("");
      qc.invalidateQueries();
    },
    onError: (e) => setNotice((e as Error).message),
  });
  const columns = useMemo(
    () => [
      col.accessor("tradeNo", { header: "Trade" }),
      col.accessor("foSystem", { header: "FO system" }),
      col.accessor("lineageRole", {
        header: "Associated row",
        cell: (x) => (
          <span
            className={"row-role " + (x.row.original.isActive ? "active" : "")}
          >
            {x.getValue() ?? "ORIGINAL"}
            {x.row.original.isActive && <b>ACTIVE</b>}
          </span>
        ),
      }),
      col.accessor("recordType", {
        header: "Record type",
        cell: (x) => <code>{x.getValue()}</code>,
      }),
      col.accessor("adjustmentBatchId", {
        header: "Adjustment batch",
        cell: (x) => x.getValue() ?? "—",
      }),
      col.accessor("targetInstrumentType", { header: "Instrument" }),
      col.accessor("isin", { header: "ISIN" }),
      col.accessor("maturityDate", { header: "Maturity" }),
      col.accessor("currency", { header: "CCY" }),
      col.accessor("amount", {
        header: "Row amount",
        cell: (x) => money.format(x.getValue()),
      }),
      col.accessor("lcrOutflow", {
        header: "LCR outflow",
        cell: (x) => money.format(x.getValue()),
      }),
      col.accessor("hqlaLevel", { header: "HQLA" }),
      col.accessor("reportingLineLcr", { header: "LCR line" }),
    ],
    [],
  );
  const table = useReactTable({
    data: trades.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  const clearContext = () => {
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
    if (!preview) return;
    setBatch((items) => [
      ...items.filter(
        (x) => x.preview.original.rowId !== preview.original.rowId,
      ),
      { preview, changes: { ...changes } },
    ]);
    setBatchPreview(null);
    setShowBatchPreview(false);
    setNotice(`${preview.original.tradeNo} added to the adjustment batch.`);
    setSelected("");
    setSubmitted(null);
    setTradeFilter("");
    setChanges({});
    setPreview(null);
  };
  const editBatchItem = (rowId: string) => {
    const item = batch.find((x) => x.preview.original.rowId === rowId);
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
          <span>developer@example</span>
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
          <span className="role">ADJUSTER</span>
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
          <div className="notice">
            <ShieldCheck />
            <span>{notice}</span>
            <button onClick={() => setNotice("")}>×</button>
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
                <div key={x.preview.original.rowId}>
                  <div>
                    <strong>{x.preview.original.tradeNo}</strong>
                    <span>
                      {x.preview.original.foSystem} ·{" "}
                      {x.preview.changedFields.map((c) => c.label).join(", ")}
                    </span>
                  </div>
                  <div>
                    <button
                      onClick={() => editBatchItem(x.preview.original.rowId)}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        setBatch((items) =>
                          items.filter(
                            (i) =>
                              i.preview.original.rowId !==
                              x.preview.original.rowId,
                          ),
                        );
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
                  onChange={(e) => setBatchReason(e.target.value)}
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
                    .length ?? 0}
                </strong>{" "}
                committed adjustments
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
                  onRevert={setRevertTarget}
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
            <div className="table-scroll">
              <table>
                <thead>
                  {table.getHeaderGroups().map((g) => (
                    <tr key={g.id}>
                      {g.headers.map((h) => (
                        <th key={h.id}>
                          {flexRender(
                            h.column.columnDef.header,
                            h.getContext(),
                          )}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {trades.isLoading ? (
                    <tr>
                      <td colSpan={9} className="empty">
                        <Loader2 className="spin" />
                        Searching this snapshot…
                      </td>
                    </tr>
                  ) : table.getRowModel().rows.length ? (
                    table.getRowModel().rows.map((r) => (
                      <tr
                        key={r.id}
                        className={
                          selected === r.original.rowId ? "selected" : ""
                        }
                        onClick={() => setSelected(r.original.rowId)}
                      >
                        {r.getVisibleCells().map((c) => (
                          <td key={c.id}>
                            {flexRender(
                              c.column.columnDef.cell,
                              c.getContext(),
                            )}
                          </td>
                        ))}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={9} className="empty">
                        No matching trade in this version.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
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
                      <button
                        className="primary"
                        onClick={() => setTab("adjustment")}
                      >
                        Create adjustment <ArrowRight />
                      </button>
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
                    </div>
                    <h3>
                      {detail.data.targetInstrumentType} ·{" "}
                      {detail.data.currency} {money.format(detail.data.amount)}
                    </h3>
                    <p>
                      {detail.data.isin} · {detail.data.portfolio} · matures{" "}
                      {detail.data.maturityDate}
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
                          {type === "select" ? (
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
                  setReason={setReason}
                  apply={() => setConfirm(true)}
                  addToBatch={addToBatch}
                  inBatch={batch.some(
                    (x) => x.preview.original.rowId === preview.original.rowId,
                  )}
                  pending={commit.isPending}
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
                          .length ?? 0}
                      </strong>{" "}
                      committed
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
                    onRevert={setRevertTarget}
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
            <h2>Apply adjustment?</h2>
            <p>
              This creates one reversal and one adjusted row for{" "}
              <strong>{preview.original.tradeNo}</strong>.
            </p>
            <div className="confirm-list">
              <span>Changed fields</span>
              <strong>
                {preview.changedFields.map((x) => x.label).join(", ")}
              </strong>
              <span>Base snapshot</span>
              <strong>
                {date} · {new Date(flow).toLocaleTimeString("en-GB")}
              </strong>
            </div>
            <p className="immutable">The original row remains unchanged.</p>
            <div className="actions">
              <button onClick={() => setConfirm(false)}>Cancel</button>
              <button
                className="primary"
                disabled={commit.isPending}
                onClick={() => commit.mutate()}
              >
                {commit.isPending && <Loader2 className="spin" />}Apply
                adjustment
              </button>
            </div>
          </div>
        </div>
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
              <strong>{revertTarget.original.tradeNo}</strong>
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
                onChange={(e) => setRevertReason(e.target.value)}
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
function RegisterEntries({
  items,
  onRevert,
  showTrade = true,
}: {
  items: HistoryItem[];
  onRevert: (item: HistoryItem) => void;
  showTrade?: boolean;
}) {
  const reverts = new Map(
    items
      .filter((x) => x.actionType === "REVERT" && x.revertedAdjustmentBatchId)
      .map((x) => [`${x.original.rowId}:${x.revertedAdjustmentBatchId}`, x]),
  );
  const commits = items.filter((x) => x.actionType !== "REVERT");
  return (
    <>
      {commits.map((commit) => {
        const revert = reverts.get(
          `${commit.original.rowId}:${commit.adjustmentBatchId}`,
        );
        const display = revert ? { ...commit, status: "REVERTED" } : commit;
        return (
          <div
            className={
              "register-pair " + (revert ? "is-reverted" : "is-committed")
            }
            key={`${commit.adjustmentBatchId}-${commit.original.rowId}`}
          >
            <HistoryEntry
              item={display}
              showTrade={showTrade}
              onRevert={revert ? undefined : onRevert}
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
}: {
  item: HistoryItem;
  showTrade?: boolean;
  onRevert?: (item: HistoryItem) => void;
}) {
  const [open, setOpen] = useState(false);
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
                  ? `${h.original.tradeNo} · ${h.adjustmentBatchId}`
                  : h.adjustmentBatchId}
              </strong>
              <span className="badge">
                {h.actionType === "REVERT" ? "REVERT" : h.status}
              </span>
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
            {onRevert && h.actionType !== "REVERT" && (
              <button className="revert-button" onClick={() => onRevert(h)}>
                Revert adjustment
              </button>
            )}
          </div>
          {open && (
            <>
              <div className="history-row-flow">
                <RowCard title="Original" row={h.original} tone="original" />
                <RowCard
                  title="Reversal"
                  row={h.cancellation}
                  tone="reversal"
                />
                <RowCard title="Adjusted" row={h.replacement} tone="adjusted" />
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
            <article key={item.original.rowId}>
              <div className="batch-preview-title">
                <div>
                  <strong>{item.original.tradeNo}</strong>
                  <span>
                    {item.original.foSystem} ·{" "}
                    {item.changedFields.map((x) => x.label).join(", ")}
                  </span>
                </div>
                <button
                  className="outline"
                  onClick={() => edit(item.original.rowId)}
                >
                  Edit adjustment
                </button>
              </div>
              <div className="batch-mini-flow">
                <RowCard title="Original" row={item.original} tone="original" />
                <RowCard
                  title="Reversal"
                  row={item.cancellation}
                  tone="reversal"
                />
                <RowCard
                  title="Adjusted"
                  row={item.replacement}
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
}: {
  preview: Preview;
  reason: string;
  setReason: (x: string) => void;
  apply: () => void;
  addToBatch: () => void;
  inBatch: boolean;
  pending: boolean;
}) {
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
        <RowCard title="Original" row={preview.original} tone="original" />
        <ArrowRight />
        <RowCard title="Reversal" row={preview.cancellation} tone="reversal" />
        <ArrowRight />
        <RowCard title="Adjusted" row={preview.replacement} tone="adjusted" />
      </div>
      <section className="changes">
        <h3>Calculation result</h3>
        {preview.differences.map((d) => (
          <div key={d.field}>
            <span>{d.label}</span>
            <span>{fmt(d.current)}</span>
            <ArrowRight />
            <strong>{fmt(d.recalculated)}</strong>
          </div>
        ))}
      </section>
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
      <div className="apply-row">
        <span>
          <ShieldCheck />
          Original row remains immutable
        </span>
        <div className="preview-actions">
          <button className="outline" onClick={addToBatch}>
            {inBatch ? "Update batch" : "Add to batch"}
          </button>
          <button
            className="primary"
            onClick={apply}
            disabled={reason.trim().length < 5 || pending}
          >
            Apply this adjustment
          </button>
        </div>
      </div>
    </div>
  );
}
