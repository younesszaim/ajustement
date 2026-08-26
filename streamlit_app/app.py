"""Streamlit UI for the intentionally small LiMon architecture."""

from __future__ import annotations

from datetime import date, datetime
import os
import time
from uuid import uuid4

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from streamlit_app.config import load_settings
from streamlit_app.client import AdjustmentApiClient, ApiError
from streamlit_app.draft_state import cancellation_signature, draft_signature
from streamlit_app.models import AdjustmentDraft, Context


st.set_page_config(page_title="LiMon Adjustment Manager", layout="wide")

# Important Streamlit mental model
# --------------------------------
# Streamlit does not keep executing at the line where a user clicks. Every
# widget interaction reruns this entire file from top to bottom. Values that
# must survive a rerun therefore live in ``st.session_state``; expensive or
# stable objects use a Streamlit cache decorator.


@st.cache_resource
def build_services():
    """Create UI-only dependencies once for the Streamlit process.

    Example: with ``LIMON_API_URL=http://127.0.0.1:8001``, the returned client
    sends every search, preview and commit to that FastAPI server.
    """
    settings = load_settings()
    client = AdjustmentApiClient(os.getenv("LIMON_API_URL", "http://127.0.0.1:8000"))
    return settings, client


def reset_draft() -> None:
    """Forget state that becomes invalid when context or selection changes."""
    for key in ("selected_row", "preview", "preview_draft", "draft_key", "draft_signature"):
        st.session_state.pop(key, None)


def display_row(row: dict, settings) -> pd.DataFrame:
    """Build a one-row display frame using business labels from YAML.

    Example: ``{"isin": "FR001"}`` is shown under ``ISIN`` rather than the
    physical database name when the configured semantic field maps to it.
    """
    labels = {settings.column(key): settings.fields[key]["label"] for key in settings.display_fields}
    return pd.DataFrame([{labels[column]: row.get(column) for column in labels}])


def change_summary(operation: dict, settings) -> str:
    """Turn an operation JSON payload into a compact register sentence."""
    changes = (operation.get("payload") or {}).get("changes") or {}
    if not changes and "new_amount" in (operation.get("payload") or {}):
        changes = {"amount": operation["payload"]["new_amount"]}
    parts = []
    for key, value in changes.items():
        label = settings.fields.get(key, {}).get("label", key.replace("_", " ").title())
        parts.append(f"{label}: {value}")
    return " · ".join(parts) if parts else "No field details recorded"


def normalized_version(value) -> str:
    """Normalize SQL and JSON timestamp spellings for history grouping.

    Both ``2026-08-07 11:14:09`` and ``2026-08-07T11:14:09`` become the same
    ISO value, so they appear in one register group.
    """
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def stage_label(stage_name: str) -> str:
    """Convert an internal stage key into a readable progress label."""
    labels = {
        "exposure_class": "Exposure class",
        "reportline_code": "Reporting line",
        "maturity_date": "Maturity date",
        "calculate_buckets": "Liquidity buckets",
        "calculate_ldp_impacts": "LDP impacts",
    }
    return labels.get(stage_name, stage_name.replace("_", " ").title())


def run_preview_with_progress(api, context, draft):
    """Start a FastAPI preview job and render its live polling state.

    Streamlit cannot receive intermediate values from a normal synchronous HTTP
    response. This helper starts a background API job, then replaces lightweight
    placeholders while polling. It returns the same preview dictionary that the
    old synchronous endpoint returned.
    """
    with st.status("Preparing calculation…", expanded=True) as status:
        progress_bar = st.progress(0)
        stage_output = st.empty()
        try:
            job = api.start_preview(context, draft)
            deadline = time.monotonic() + 120
            while True:
                job = api.preview_status(job["job_id"])
                completed = job.get("completed_stages") or []
                current = job.get("current_stage")
                lines = [f"✓ {stage_label(stage)}" for stage in completed]
                if current and current not in completed:
                    lines.append(f"→ {stage_label(current)}")
                stage_output.markdown("  \n".join(lines) or "Waiting for a calculation worker…")
                progress_bar.progress(int(job.get("progress") or 0))

                if job["status"] == "COMPLETED":
                    status.update(label="Calculation completed", state="complete", expanded=False)
                    return job["result"]
                if job["status"] == "FAILED":
                    status.update(label="Calculation failed", state="error", expanded=True)
                    st.error(job.get("error") or "The calculation failed without an error message.")
                    return None
                if time.monotonic() >= deadline:
                    status.update(label="Calculation is taking too long", state="error", expanded=True)
                    st.error("Preview polling stopped after 120 seconds. The API job may still be running.")
                    return None

                # Polling is intentionally modest: frequent enough for a smooth
                # single-user UI without flooding FastAPI with status requests.
                time.sleep(0.4)
        except ApiError as exc:
            status.update(label="Preview could not start", state="error", expanded=True)
            st.error(str(exc))
            return None


@st.dialog("Adjustment review", width="large")
def review_adjustment(operation: dict, settings):
    """Render the large, read-only audit dialog for one operation."""
    # Everything shown here comes from the single PostgreSQL operation row.
    # Reviewing history therefore does not trigger a large output-table query.
    status = operation.get("status", "UNKNOWN")
    st.subheader(f"{operation.get('operation_type', 'Adjustment')} · {status}")
    first, second, third = st.columns(3)
    first.metric("As-of date", str(operation.get("asofdate", "—")))
    second.metric("Version", str(operation.get("version", "—")))
    third.metric("FO system", str(operation.get("fo_system", "—")))
    st.caption(
        f"Created by {operation.get('created_by', '—')} on "
        f"{operation.get('created_at', '—')} · Leg: "
        f"{'Cash' if operation.get('leg_flag') == 0 else 'Titre'}"
    )
    st.markdown("**Changes**")
    changes = (operation.get("payload") or {}).get("changes") or {}
    if changes:
        rows = [
            {
                "Field": settings.fields.get(key, {}).get("label", key),
                "Adjusted value": str(value),
            }
            for key, value in changes.items()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.write(change_summary(operation, settings))
    st.markdown("**Reason**")
    st.write(operation.get("reason") or "—")
    st.markdown("**Audit references**")
    st.code(
        f"Operation: {operation.get('operation_id')}\n"
        f"Source row: {operation.get('source_output_id')}\n"
        f"Generated rows: {operation.get('output_ids') or []}"
    )
    if operation.get("error_message"):
        st.error(operation["error_message"])


@st.dialog("Revert committed adjustment")
def revert_adjustment_dialog(operation: dict, api):
    """Collect explicit confirmation and submit one idempotent revert."""
    if operation.get("operation_type") == "CANCEL":
        st.warning(
            "This restores the cancelled trade as a new active audited row. "
            "The cancellation and original history are never deleted."
        )
    else:
        st.warning(
            "This appends a reversal of the adjusted row and a restored copy of the original row. "
            "Existing history is never deleted."
        )
    st.caption(
        f"{operation.get('fo_system')} · {operation.get('asofdate')} · "
        f"{operation.get('version')}"
    )
    revert_reason = st.text_area(
        "Revert reason",
        placeholder="Explain why this adjustment must be reverted",
        key=f"revert-reason-{operation['operation_id']}",
    )
    confirmed = st.checkbox(
        "I understand that this creates new audited output rows.",
        key=f"revert-confirm-{operation['operation_id']}",
    )
    key_name = f"revert-key-{operation['operation_id']}"
    if key_name not in st.session_state:
        # As for a normal commit, keep the same key across reruns and retries of
        # this exact revert dialog. FastAPI uses it as adjustment_reference.
        st.session_state[key_name] = str(uuid4())
    if st.button(
        "Revert adjustment",
        type="primary",
        disabled=not revert_reason.strip() or not confirmed,
        use_container_width=True,
    ):
        try:
            result = api.revert(
                operation["operation_id"], revert_reason.strip(), st.session_state[key_name]
            )
            st.session_state.register_success = (
                f"Revert {result['operation_id']} is {result['status']}."
            )
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))


@st.dialog("Cancel selected trade")
def cancel_trade_dialog(context, selected_row: dict, settings, api):
    """Confirm and commit cancellation without a separate preview button."""
    source_id = str(selected_row[settings.column("output_id")])
    st.error(
        "This action neutralizes the complete active business effect. It appends "
        "one reversal row and does not create a replacement row."
    )
    st.dataframe(display_row(selected_row, settings), hide_index=True, use_container_width=True)
    reason = st.text_area(
        "Cancellation reason",
        placeholder="Explain why this trade must be cancelled",
        key=f"cancel-reason-{source_id}",
    )
    confirmed = st.checkbox(
        "I understand that the trade will have no active row until this cancellation is reverted.",
        key=f"cancel-confirm-{source_id}",
    )
    signature_name = f"cancel-signature-{source_id}"
    key_name = f"cancel-key-{source_id}"
    if st.button(
        "⛔ Confirm cancellation",
        type="primary",
        disabled=not reason.strip() or not confirmed,
        use_container_width=True,
    ):
        signature = cancellation_signature(
            context=context,
            source_output_id=source_id,
            reason=reason,
        )
        if st.session_state.get(signature_name) != signature:
            st.session_state[key_name] = str(uuid4())
            st.session_state[signature_name] = signature
        try:
            result = api.cancel(
                context, source_id, reason.strip(), st.session_state[key_name]
            )
            st.session_state.workspace_success = (
                f"Cancellation {result['operation_id']} is {result['status']}."
            )
            st.session_state.pop("search_results", None)
            reset_draft()
            st.rerun()
        except ApiError as exc:
            # Keep key + signature for an exact retry after an uncertain error.
            st.error(str(exc))


st.title("LiMon Adjustment Manager")
st.caption("Simple architecture · output table + one PostgreSQL operation table")

# This block runs on every Streamlit rerun, but ``build_services`` returns its
# cached settings/client pair. The UI only knows the HTTP client: database and
# calculation dependencies are created in the FastAPI process.
try:
    settings, api = build_services()
except Exception as exc:
    st.error(f"UI configuration error: {exc}")
    st.stop()

workspace, register = st.tabs(["Adjustment workspace", "Adjustment register"])

# =============================================================================
# TAB 1 — ADJUSTMENT WORKSPACE
# =============================================================================
# The screen is intentionally ordered like a funnel:
# snapshot context -> server-side search -> one selected row -> draft -> preview
# -> commit. A downstream section is rendered only when its upstream data exists.
with workspace:
    if st.session_state.get("workspace_success"):
        st.success(st.session_state.pop("workspace_success"))
    st.subheader("1. Choose the output context")

    # Dates, versions and FO systems come from the output database through the
    # API. Nothing is hard-coded, so an empty output produces an empty screen.
    try:
        available_dates = api.asofdates()
    except ApiError as exc:
        st.error(str(exc))
        st.stop()

    if not available_dates:
        st.info("The output table is empty. No hard-coded example is displayed.")
        st.stop()

    valid_dates = {str(value)[:10] for value in available_dates}
    selected_date = st.date_input("As-of date", value=date.fromisoformat(max(valid_dates)))
    if selected_date.isoformat() not in valid_dates:
        st.warning("No output exists for this date.")
        st.stop()

    # Cascading widgets prevent invalid combinations: version depends on date,
    # and FO system depends on both date and version.
    versions = api.versions(selected_date.isoformat())
    version = st.selectbox("Version", versions, format_func=str)
    fo_systems = api.fo_systems(selected_date.isoformat(), str(version))
    left, right = st.columns(2)
    fo_system = left.selectbox("FO system", fo_systems)
    leg_label = right.selectbox("Leg", ["Cash", "Titre"])
    leg_flag = 0 if leg_label == "Cash" else 1
    context = Context(selected_date.isoformat(), str(version), str(fo_system), leg_flag)

    # A row selected under another snapshot must never remain selectable after
    # the user changes a context widget. The signature detects such a change
    # during the current top-to-bottom rerun and invalidates all downstream data.
    context_signature = (context.asofdate, context.version, context.fo_system, context.leg_flag)
    if st.session_state.get("context_signature") != context_signature:
        st.session_state.context_signature = context_signature
        st.session_state.pop("search_results", None)
        reset_draft()

    st.subheader("2. Find and select a trade")

    # These columns align the input and actions without custom HTML/CSS.
    search_col, search_button_col, clear_button_col = st.columns([6, 1, 1], vertical_alignment="bottom")
    search_text = search_col.text_input("Trade or ISIN", key="search_text")
    run_search = search_button_col.button("Search", use_container_width=True)
    if clear_button_col.button("Clear", use_container_width=True):
        # Assigning the widget's session key clears its visible value on the
        # next explicit rerun. Search results and draft state must follow it.
        st.session_state.search_text = ""
        st.session_state.pop("search_results", None)
        reset_draft()
        st.rerun()

    if run_search or "search_results" not in st.session_state:
        # FastAPI/SQL applies context and text filtering. Only a bounded result
        # set reaches Streamlit, which is essential for large LiMon as-of dates.
        try:
            st.session_state.search_results = api.trades(context, search_text)
        except ApiError as exc:
            st.error(str(exc))
            st.session_state.search_results = []
        reset_draft()

    rows = st.session_state.get("search_results", [])
    if not rows:
        st.info("No active trade matches this context and search.")
    else:
        # AG Grid adds convenient local sorting/filtering to the already bounded
        # API result. It is not the primary database search engine.
        frame = display_row(rows[0], settings).iloc[0:0]
        frame = pd.concat([frame, *[display_row(row, settings) for row in rows]], ignore_index=True)
        grid = GridOptionsBuilder.from_dataframe(frame)
        grid.configure_default_column(filter=True, sortable=True, resizable=True)
        grid.configure_selection(selection_mode="single", use_checkbox=True)
        response = AgGrid(
            frame,
            gridOptions=grid.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            height=min(420, 85 + len(frame) * 32),
            theme="streamlit",
        )
        selected = response.get("selected_rows")
        # streamlit-aggrid versions may return either a DataFrame or a list of
        # dictionaries. Normalizing here keeps the rest of the UI independent
        # of that library detail.
        if isinstance(selected, pd.DataFrame):
            selected = selected.to_dict("records")
        if selected:
            # The grid contains user-facing labels, while the API row contains
            # physical column names. Resolve the selection through the configured
            # output ID instead of trying to rebuild a business row from the grid.
            selected_id_label = settings.fields["output_id"]["label"]
            selected_id = str(selected[0][selected_id_label])
            st.session_state.selected_row = next(
                row for row in rows if str(row[settings.column("output_id")]) == selected_id
            )

    selected_row = st.session_state.get("selected_row")
    if selected_row:
        st.subheader("3. Adjust the selected active row")
        st.dataframe(display_row(selected_row, settings), hide_index=True, use_container_width=True)

        # Leg is immutable context, not an adjustable field. It decides whether
        # the numeric editor targets Cash amount or Security amount.
        amount_key = "cash_amount_eur" if context.leg_flag == 0 else "security_amount_eur"
        amount_column = settings.column(amount_key)
        amount_label = settings.fields[amount_key]["label"]
        selected_output_id = str(selected_row[settings.column("output_id")])
        # A form batches widget changes in the browser. Typing a reason or
        # choosing several values therefore does not rerun the complete app;
        # Python receives the complete draft only when Preview is submitted.
        with st.form(
            key=f"adjustment-form-{selected_output_id}",
            clear_on_submit=False,
            enter_to_submit=False,
        ):
            new_amount = st.number_input(
                amount_label,
                value=float(selected_row.get(amount_column) or 0),
                step=1000.0,
            )
            field_changes = {}
            # Controlled dropdowns are generated from YAML. Adding another
            # configured field does not require another widget block.
            for definition in settings.editable_fields:
                field_key = definition["field"]
                column = settings.column(field_key)
                current = selected_row.get(column)
                options = list(dict.fromkeys([current, *definition.get("options", [])]))
                selected_value = st.selectbox(
                    settings.fields[field_key]["label"],
                    options,
                    index=0,
                    key=f"edit-{selected_output_id}-{field_key}",
                )
                if selected_value != current:
                    # Send only actual differences. FastAPI rebuilds and
                    # validates the complete adjusted row authoritatively.
                    field_changes[field_key] = selected_value
            reason = st.text_area(
                "Reason",
                placeholder="Explain why this adjustment is required",
                key=f"reason-{selected_output_id}",
            )
            preview_clicked = st.form_submit_button("Preview adjustment", type="primary")

        cancel_col, _ = st.columns([1, 4])
        if cancel_col.button(
            "⛔ Cancel trade",
            key=f"cancel-trade-{selected_output_id}",
            type="primary",
            use_container_width=True,
        ):
            cancel_trade_dialog(context, selected_row, settings, api)

        if preview_clicked:
            # A newly submitted draft invalidates the former preview before any
            # validation or API call. Commit can never use a stale result.
            st.session_state.pop("preview", None)
            st.session_state.pop("preview_draft", None)
            has_changes = (
                new_amount != float(selected_row.get(amount_column) or 0)
                or bool(field_changes)
            )
            if not reason.strip():
                st.error("A reason is required before preview.")
            elif not has_changes:
                st.error("Change at least one value before preview.")
            else:
                # One retry key belongs to one complete intention. An unchanged
                # retry keeps it; editing a value or reason creates a new one.
                signature = draft_signature(
                    context=context,
                    source_output_id=selected_output_id,
                    new_amount=new_amount,
                    changes=field_changes,
                    reason=reason,
                )
                if st.session_state.get("draft_signature") != signature:
                    st.session_state.draft_key = str(uuid4())
                    st.session_state.draft_signature = signature
                draft = AdjustmentDraft(
                    source_output_id=selected_output_id,
                    new_amount=new_amount,
                    reason=reason.strip(),
                    idempotency_key=st.session_state.draft_key,
                    changes=field_changes,
                )
                preview_result = run_preview_with_progress(api, context, draft)
                if preview_result is not None:
                    st.session_state.preview = preview_result
                    # Commit must use exactly the intention that produced this
                    # authoritative preview, even if the visible form is edited
                    # again without being submitted.
                    st.session_state.preview_draft = draft

        preview = st.session_state.get("preview")
        if preview:
            st.subheader("4. Preview the impact")
            calculation_steps = preview.get("calculation_steps") or []
            if calculation_steps:
                st.caption("Calculation path: " + " → ".join(calculation_steps))
            # The three tabs deliberately mirror the append-only journal. The
            # original is informational; commit inserts reversal and adjusted.
            original_tab, reversal_tab, adjusted_tab = st.tabs(["Original", "Reversal", "Adjusted"])
            with original_tab:
                st.dataframe(display_row(preview["original"], settings), hide_index=True, use_container_width=True)
            with reversal_tab:
                st.dataframe(display_row(preview["reversal"], settings), hide_index=True, use_container_width=True)
            with adjusted_tab:
                st.dataframe(display_row(preview["adjusted"], settings), hide_index=True, use_container_width=True)
            st.caption("Change the amount or reason and run preview again before committing.")
            if st.button("Commit adjustment", type="primary"):
                try:
                    # Commit sends the same context, changes and idempotency key
                    # used for preview. The API still re-reads the active row and
                    # rebuilds the calculation to protect against stale data.
                    result = api.commit(context, st.session_state.preview_draft)
                    st.success(f"Adjustment {result['operation_id']} is {result['status']}.")
                    st.session_state.pop("search_results", None)
                    reset_draft()
                except ApiError as exc:
                    st.error(str(exc))

# =============================================================================
# TAB 2 — ADJUSTMENT REGISTER
# =============================================================================
# PostgreSQL contains one operation per user intention. Streamlit groups those
# operation rows for readability; it never attempts to reconstruct audit state
# by scanning all business rows in the output table.
with register:
    st.subheader("Adjustment register")
    st.caption("History grouped by as-of date and version. Open an operation to review its details.")
    if st.session_state.get("register_success"):
        st.success(st.session_state.pop("register_success"))
    try:
        operations = api.adjustments()
    except ApiError as exc:
        st.error(str(exc))
    else:
        if not operations:
            st.info("No adjustment has been recorded.")
        else:
            # Filtering is presentation-only for the current small history. The
            # API already caps the response at 1,000 rows; production-scale audit
            # history should move grouping and pagination into FastAPI/SQL.
            available_register_dates = sorted(
                {str(operation["asofdate"])[:10] for operation in operations}, reverse=True
            )
            date_filter = st.selectbox(
                "As-of date",
                ["All dates", *available_register_dates],
                key="register-date-filter",
            )
            filtered = [
                operation
                for operation in operations
                if date_filter == "All dates"
                or str(operation["asofdate"])[:10] == date_filter
            ]
            committed = sum(operation["status"] == "COMMITTED" for operation in filtered)
            failed = sum(operation["status"] in ("FAILED", "RECONCILIATION_REQUIRED") for operation in filtered)
            metric_one, metric_two, metric_three = st.columns(3)
            metric_one.metric("Adjustments", len(filtered))
            metric_two.metric("Committed", committed)
            metric_three.metric("Attention required", failed)

            groups = {}
            for operation in filtered:
                # Old records may store a timestamp with a space, while JSON uses
                # ``T``. Normalize before grouping to avoid duplicate version cards.
                key = (str(operation["asofdate"])[:10], normalized_version(operation["version"]))
                groups.setdefault(key, []).append(operation)
            for (asofdate, version), group in groups.items():
                latest = max(str(operation.get("created_at") or "") for operation in group)
                title = f"{asofdate} · {version}  —  {len(group)} adjustment(s) · latest {latest[:16]}"
                with st.expander(title):
                    for operation in group:
                        # Each operation receives one compact summary card and two
                        # independent actions. Review is read-only. Revert appears
                        # only while a replacement remains committed.
                        with st.container(border=True):
                            status_col, detail_col, actor_col, action_col = st.columns([1, 4, 2, 2])
                            status_col.markdown(f"**{operation['status']}**")
                            detail_col.markdown(f"**{operation['operation_type']}** · {change_summary(operation, settings)}")
                            detail_col.caption(
                                f"{operation.get('fo_system')} · "
                                f"{'Cash' if operation.get('leg_flag') == 0 else 'Titre'} · "
                                f"{str(operation.get('created_at') or '')[:19]}"
                            )
                            actor_col.write(operation.get("created_by") or "—")
                            review_col, revert_col = action_col.columns(2)
                            if review_col.button(
                                "Review",
                                key=f"review-{operation['operation_id']}",
                                use_container_width=True,
                            ):
                                review_adjustment(operation, settings)
                            can_revert = (
                                operation.get("status") == "COMMITTED"
                                and operation.get("operation_type") in {"REPLACE", "CANCEL"}
                            )
                            if can_revert and revert_col.button(
                                "Revert",
                                key=f"revert-{operation['operation_id']}",
                                type="primary",
                                use_container_width=True,
                            ):
                                revert_adjustment_dialog(operation, api)
