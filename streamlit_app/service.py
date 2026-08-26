"""Adjustment rules. Preview and commit deliberately share ``_build_rows``."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from importlib import import_module
from uuid import uuid4

from .models import CancellationPreview, Preview


class AdjustmentError(Exception):
    """Business conflict safe to expose to an API/UI caller."""

    pass


def load_callable(path: str):
    """Load a configured ``module:function`` calculation entry point."""
    module_name, function_name = path.split(":", 1)
    return getattr(import_module(module_name), function_name)


class AdjustmentService:
    """Framework-independent preview, commit, retry and revert workflows."""

    def __init__(self, output_store, operation_store, settings, calculator=None):
        """Inject storage and calculation dependencies for easy unit testing."""
        self.output = output_store
        self.operations = operation_store
        self.settings = settings
        self.calculator = calculator or load_callable(settings.calculation_callable)

    def preview(
        self,
        context,
        draft,
        progress_callback=None,
        delay_seconds: float = 0.0,
    ) -> Preview:
        """Re-read and transform an active row without durable writes.

        For an original amount of 100 and requested amount of 250, the result
        contains original 100, reversal -100 and adjusted 250.
        """
        original = self.output.get_active(draft.source_output_id)
        if original is None:
            raise AdjustmentError("The selected output row is no longer active. Refresh the search.")
        self._validate_context(original, context)
        return self._build_rows(
            original,
            draft,
            progress_callback=progress_callback,
            delay_seconds=delay_seconds,
        )

    def commit(self, context, draft) -> dict:
        """Persist one idempotent replacement and its audit operation.

        Calling this method twice with the same idempotency key returns the
        existing operation and never appends a second pair of output rows.
        """
        existing = self.operations.find_by_key(draft.idempotency_key)
        requested_changes = self._requested_changes(context.leg_flag, draft)
        if existing:
            self._validate_retry_intention(existing, context, draft, requested_changes)
            if existing["status"] == "COMMITTED":
                return existing

        output_id = self.settings.column("output_id")
        deterministic_ids = [f"REV-{draft.idempotency_key}", f"ADJ-{draft.idempotency_key}"]
        if existing and self.output.reference_exists(draft.idempotency_key):
            try:
                self.operations.set_status(
                    str(existing["operation_id"]), "COMMITTED", output_ids=deterministic_ids
                )
            except Exception as exc:
                raise AdjustmentError(
                    "Output rows exist but PostgreSQL confirmation still fails. Reconciliation is required."
                ) from exc
            return {
                "operation_id": str(existing["operation_id"]),
                "status": "COMMITTED",
                "output_ids": deterministic_ids,
            }
        preview = self.preview(context, draft)
        if existing:
            operation_id = str(existing["operation_id"])
        else:
            operation_id = str(uuid4())
            operation = {
                "operation_id": operation_id,
                "idempotency_key": draft.idempotency_key,
                "operation_type": "REPLACE",
                "asofdate": context.asofdate,
                "version": context.version,
                "fo_system": context.fo_system,
                "leg_flag": context.leg_flag,
                "source_output_id": draft.source_output_id,
                "reason": draft.reason,
                "created_by": self.settings.actor,
                "payload": {"changes": requested_changes},
            }
            self.operations.create(operation)

        reference = draft.idempotency_key
        if not self.output.reference_exists(reference):
            try:
                self.output.append([preview.reversal, preview.adjusted])
            except Exception as exc:
                self.operations.set_status(operation_id, "FAILED", error_message=str(exc))
                raise AdjustmentError("The output write failed; no adjustment was committed.") from exc

        ids = [preview.reversal[output_id], preview.adjusted[output_id]]
        try:
            self.operations.set_status(operation_id, "COMMITTED", output_ids=ids)
        except Exception as exc:
            raise AdjustmentError(
                "Output rows exist but PostgreSQL confirmation failed. Reconciliation is required."
            ) from exc
        return {"operation_id": operation_id, "status": "COMMITTED", "output_ids": ids}

    def preview_cancel(self, context, source_output_id: str) -> CancellationPreview:
        """Build the one reversal that would neutralize an active output row."""
        original = self.output.get_active(source_output_id)
        if original is None:
            raise AdjustmentError(
                "The selected output row is no longer active. Refresh the search."
            )
        self._validate_context(original, context)
        return CancellationPreview(
            original=deepcopy(original),
            reversal=self._build_cancel_row(original, "PREVIEW"),
        )

    def commit_cancel(self, context, draft) -> dict:
        """Append one idempotent reversal and audit a trade cancellation."""
        existing = self.operations.find_by_key(draft.idempotency_key)
        expected_changes = {"business_effect": "CANCELLED"}
        if existing:
            self._validate_cancel_retry(existing, context, draft, expected_changes)
            if existing["status"] == "COMMITTED":
                return existing

        output_id = self.settings.column("output_id")
        deterministic_ids = [f"REV-{draft.idempotency_key}"]
        if existing and self.output.reference_exists(draft.idempotency_key):
            try:
                self.operations.set_status(
                    str(existing["operation_id"]), "COMMITTED", output_ids=deterministic_ids
                )
            except Exception as exc:
                raise AdjustmentError(
                    "Cancellation output exists but PostgreSQL confirmation still fails. "
                    "Reconciliation is required."
                ) from exc
            return {
                "operation_id": str(existing["operation_id"]),
                "status": "COMMITTED",
                "output_ids": deterministic_ids,
            }

        original = self.output.get_active(draft.source_output_id)
        if original is None:
            raise AdjustmentError(
                "The selected output row is no longer active. Refresh the search."
            )
        self._validate_context(original, context)
        reversal = self._build_cancel_row(original, draft.idempotency_key)

        if existing:
            operation_id = str(existing["operation_id"])
        else:
            operation_id = str(uuid4())
            self.operations.create(
                {
                    "operation_id": operation_id,
                    "idempotency_key": draft.idempotency_key,
                    "operation_type": "CANCEL",
                    "asofdate": context.asofdate,
                    "version": context.version,
                    "fo_system": context.fo_system,
                    "leg_flag": context.leg_flag,
                    "source_output_id": draft.source_output_id,
                    "reason": draft.reason.strip(),
                    "created_by": self.settings.actor,
                    "payload": {"changes": expected_changes},
                }
            )

        if not self.output.reference_exists(draft.idempotency_key):
            try:
                self.output.append([reversal])
            except Exception as exc:
                self.operations.set_status(operation_id, "FAILED", error_message=str(exc))
                raise AdjustmentError(
                    "The cancellation output write failed; the trade was not cancelled."
                ) from exc
        ids = [str(reversal[output_id])]
        try:
            self.operations.set_status(operation_id, "COMMITTED", output_ids=ids)
        except Exception as exc:
            raise AdjustmentError(
                "The cancellation row exists but PostgreSQL confirmation failed. "
                "Reconciliation is required."
            ) from exc
        return {"operation_id": operation_id, "status": "COMMITTED", "output_ids": ids}

    def _validate_cancel_retry(self, existing, context, draft, expected_changes) -> None:
        """Ensure a cancellation retry key still represents the same intent."""
        expected = {
            "operation_type": "CANCEL",
            "source_output_id": str(draft.source_output_id),
            "asofdate": self._context_value(context.asofdate),
            "version": self._context_value(context.version),
            "fo_system": str(context.fo_system),
            "leg_flag": int(context.leg_flag),
            "reason": draft.reason.strip(),
        }
        mismatches = []
        for field, requested in expected.items():
            if field not in existing:
                continue
            stored = existing.get(field)
            if field in {"asofdate", "version"}:
                stored = self._context_value(stored)
            elif field == "leg_flag":
                stored = int(stored)
            else:
                stored = str(stored).strip() if stored is not None else ""
            if stored != requested:
                mismatches.append(field)
        if (existing.get("payload") or {}).get("changes") != expected_changes:
            mismatches.append("field changes")
        if mismatches:
            raise AdjustmentError(
                "This retry key belongs to a different cancellation intention "
                f"({', '.join(mismatches)}). Confirm the modified cancellation again "
                "to create a new retry key."
            )

    def _validate_retry_intention(self, existing, context, draft, requested_changes) -> None:
        """Prevent one retry key from representing two different adjustments.

        This runs before the COMMITTED and reconciliation fast paths. Without
        that ordering, a modified request could receive an older operation's
        success response or reconcile rows created for another intention.
        """
        payload = existing.get("payload") or {}
        stored_changes = payload.get("changes")
        if stored_changes is None:  # compatibility with the first prototype payload
            amount_key = "cash_amount_eur" if context.leg_flag == 0 else "security_amount_eur"
            stored_changes = {amount_key: payload.get("new_amount")}

        expected = {
            "operation_type": "REPLACE",
            "source_output_id": str(draft.source_output_id),
            "asofdate": self._context_value(context.asofdate),
            "version": self._context_value(context.version),
            "fo_system": str(context.fo_system),
            "leg_flag": int(context.leg_flag),
            "reason": draft.reason.strip(),
        }
        mismatches = []
        for field, requested in expected.items():
            # Missing fields are tolerated for legacy prototype rows and small
            # repository fakes; the current SQL store always returns all fields.
            if field not in existing:
                continue
            stored = existing.get(field)
            if field in {"asofdate", "version"}:
                stored = self._context_value(stored)
            elif field == "leg_flag":
                stored = int(stored)
            else:
                stored = str(stored).strip() if stored is not None else ""
            if stored != requested:
                mismatches.append(field)
        if stored_changes != requested_changes:
            mismatches.append("field changes")
        if mismatches:
            raise AdjustmentError(
                "This retry key belongs to a different adjustment intention "
                f"({', '.join(mismatches)}). Preview the modified draft again "
                "to create a new retry key."
            )

    def revert(self, target_operation_id: str, reason: str, idempotency_key: str) -> dict:
        """Append a reversal of the adjusted row and restore the original row."""
        existing = self.operations.find_by_key(idempotency_key)
        if existing:
            existing_target = (existing.get("payload") or {}).get("reverts_operation_id")
            if existing_target != target_operation_id:
                raise AdjustmentError("This retry key belongs to a different operation.")
            if existing["status"] == "COMMITTED":
                return existing

        target = self.operations.get_operation(target_operation_id)
        if target is None:
            raise AdjustmentError("The adjustment to revert was not found.")
        if target["operation_type"] not in {"REPLACE", "CANCEL"}:
            raise AdjustmentError("Only a committed replacement or cancellation can be reverted.")
        is_cancel_revert = target["operation_type"] == "CANCEL"
        deterministic_ids = (
            [f"ADJ-{idempotency_key}"]
            if is_cancel_revert
            else [f"REV-{idempotency_key}", f"ADJ-{idempotency_key}"]
        )

        if existing and self.output.reference_exists(idempotency_key):
            try:
                self.operations.commit_revert(
                    str(existing["operation_id"]), target_operation_id, deterministic_ids
                )
            except Exception as exc:
                raise AdjustmentError(
                    "Revert output rows exist but PostgreSQL confirmation still fails."
                ) from exc
            return {
                "operation_id": str(existing["operation_id"]),
                "status": "COMMITTED",
                "output_ids": deterministic_ids,
            }

        if target["status"] != "COMMITTED":
            raise AdjustmentError("This adjustment is not committed or has already been reverted.")
        required_output_count = 1 if is_cancel_revert else 2
        if not target.get("output_ids") or len(target["output_ids"]) < required_output_count:
            raise AdjustmentError("The adjustment does not contain its generated output IDs.")
        original = self.output.get_by_id(str(target["source_output_id"]))
        if original is None:
            raise AdjustmentError("The original output row required for restoration was not found.")
        if is_cancel_revert:
            cancellation_id = str(target["output_ids"][-1])
            cancellation = self.output.get_by_id(cancellation_id)
            if cancellation is None:
                raise AdjustmentError("The cancellation row required for revert was not found.")
            rows = [self._build_cancel_revert_row(original, cancellation, idempotency_key)]
            revert_source_id = cancellation_id
        else:
            active_adjusted_id = str(target["output_ids"][-1])
            active_adjusted = self.output.get_active(active_adjusted_id)
            if active_adjusted is None:
                raise AdjustmentError("The adjusted row is no longer active and cannot be reverted.")
            rows = list(self._build_revert_rows(original, active_adjusted, idempotency_key))
            revert_source_id = active_adjusted_id
        if existing:
            revert_operation_id = str(existing["operation_id"])
        else:
            revert_operation_id = str(uuid4())
            self.operations.create(
                {
                    "operation_id": revert_operation_id,
                    "idempotency_key": idempotency_key,
                    "operation_type": "REVERT",
                    "asofdate": target["asofdate"],
                    "version": target["version"],
                    "fo_system": target["fo_system"],
                    "leg_flag": target["leg_flag"],
                    "source_output_id": revert_source_id,
                    "reason": reason,
                    "created_by": self.settings.actor,
                    "payload": {
                        "reverts_operation_id": target_operation_id,
                        "restored_source_output_id": target["source_output_id"],
                    },
                    "reverts_operation_id": target_operation_id,
                }
            )

        if not self.output.reference_exists(idempotency_key):
            try:
                self.output.append(rows)
            except Exception as exc:
                self.operations.set_status(revert_operation_id, "FAILED", error_message=str(exc))
                raise AdjustmentError("The revert output write failed; retry the same intention.") from exc
        try:
            self.operations.commit_revert(
                revert_operation_id, target_operation_id, deterministic_ids
            )
        except Exception as exc:
            raise AdjustmentError(
                "Revert rows exist but PostgreSQL confirmation failed. Retry reconciliation."
            ) from exc
        return {
            "operation_id": revert_operation_id,
            "status": "COMMITTED",
            "output_ids": deterministic_ids,
        }

    def _validate_context(self, row: dict, context) -> None:
        """Prevent a row selected in one snapshot being written into another."""
        expected = {
            self.settings.column("asofdate"): str(context.asofdate),
            self.settings.column("version"): str(context.version),
            self.settings.column("fo_system"): str(context.fo_system),
            self.settings.column("leg_flag"): str(context.leg_flag),
        }
        for column, value in expected.items():
            if self._context_value(row.get(column)) != self._context_value(value):
                raise AdjustmentError("The selected row does not belong to the current context.")

    @staticmethod
    def _context_value(value) -> str:
        """Compare dates/versions by value, independent of SQL/JSON formatting."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        try:
            if len(text) == 10:
                return date.fromisoformat(text).isoformat()
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return text

    def _build_rows(
        self,
        original: dict,
        draft,
        progress_callback=None,
        delay_seconds: float = 0.0,
    ) -> Preview:
        """Build the exact original/reversal/adjusted journal used everywhere."""
        f, t = self.settings.fields, self.settings.technical_fields
        output_id = f["output_id"]["column"]
        source_id = str(original[output_id])
        reversal = deepcopy(original)
        reversal[output_id] = f"REV-{draft.idempotency_key}"
        reversal[t["record_type"]] = self.settings.record_types["reversal"]
        reversal[t["adjustment_reference"]] = draft.idempotency_key
        reversal[t["source_output_id"]] = source_id
        reversal[t["parent_output_id"]] = source_id
        for column, value in original.items():
            if self.settings.is_additive(column):
                reversal[column] = -float(value or 0)

        adjusted = deepcopy(original)
        adjusted[output_id] = f"ADJ-{draft.idempotency_key}"
        adjusted[t["record_type"]] = self.settings.record_types["adjusted"]
        adjusted[t["adjustment_reference"]] = draft.idempotency_key
        adjusted[t["source_output_id"]] = source_id
        adjusted[t["parent_output_id"]] = source_id
        leg = int(original[f["leg_flag"]["column"]])
        requested_changes = self._requested_changes(leg, draft)
        actual_changes = {
            field_key: value
            for field_key, value in requested_changes.items()
            if original.get(f[field_key]["column"]) != value
        }
        if not actual_changes:
            raise AdjustmentError("At least one field must have a different value.")
        for field_key, value in requested_changes.items():
            adjusted[f[field_key]["column"]] = value
        calculation_result = self.calculator(
            adjusted,
            {key: value["column"] for key, value in f.items()},
            actual_changes,
            progress_callback,
            delay_seconds,
        )
        if isinstance(calculation_result, tuple):
            adjusted, calculation_steps = calculation_result
        else:  # Temporary compatibility for a custom legacy two-value result.
            adjusted, calculation_steps = calculation_result, []
        return Preview(
            original=deepcopy(original),
            reversal=reversal,
            adjusted=adjusted,
            calculation_steps=calculation_steps,
        )

    def _build_cancel_row(self, original: dict, key: str) -> dict:
        """Copy an active row and negate every configured additive measure."""
        f, t = self.settings.fields, self.settings.technical_fields
        output_id = f["output_id"]["column"]
        source_id = str(original[output_id])
        reversal = deepcopy(original)
        reversal[output_id] = f"REV-{key}"
        reversal[t["record_type"]] = self.settings.record_types["reversal"]
        reversal[t["adjustment_reference"]] = key
        reversal[t["source_output_id"]] = source_id
        reversal[t["parent_output_id"]] = source_id
        for column, value in original.items():
            if self.settings.is_additive(column):
                reversal[column] = -float(value or 0)
        return reversal

    def _requested_changes(self, leg: int, draft) -> dict:
        """Validate semantic changes and select the leg-specific amount field.

        Example: leg ``1`` maps ``new_amount`` to ``security_amount_eur``;
        exposure class is accepted only when listed in project YAML.
        """
        amount_key = "cash_amount_eur" if int(leg) == 0 else "security_amount_eur"
        changes = {amount_key: float(draft.new_amount)}
        definitions = {item["field"]: item for item in self.settings.editable_fields}
        for field_key, value in draft.changes.items():
            if field_key not in definitions or field_key not in self.settings.fields:
                raise AdjustmentError(f'Field "{field_key}" is not adjustable.')
            definition = definitions[field_key]
            options = definition.get("options")
            if options and value not in options:
                raise AdjustmentError(
                    f'Value "{value}" is not allowed for {self.settings.fields[field_key]["label"]}.'
                )
            changes[field_key] = value
        return changes

    def _build_revert_rows(self, original: dict, active_adjusted: dict, key: str):
        """Build ``-adjusted + restored original`` without mutating history."""
        f, t = self.settings.fields, self.settings.technical_fields
        output_id = f["output_id"]["column"]
        original_id = str(original[output_id])
        adjusted_id = str(active_adjusted[output_id])

        reversal = deepcopy(active_adjusted)
        reversal[output_id] = f"REV-{key}"
        reversal[t["record_type"]] = self.settings.record_types["reversal"]
        reversal[t["adjustment_reference"]] = key
        reversal[t["source_output_id"]] = original_id
        reversal[t["parent_output_id"]] = adjusted_id
        for column, value in active_adjusted.items():
            if self.settings.is_additive(column):
                reversal[column] = -float(value or 0)

        restored = deepcopy(original)
        restored[output_id] = f"ADJ-{key}"
        restored[t["record_type"]] = self.settings.record_types["adjusted"]
        restored[t["adjustment_reference"]] = key
        restored[t["source_output_id"]] = original_id
        restored[t["parent_output_id"]] = adjusted_id
        return reversal, restored

    def _build_cancel_revert_row(
        self, original: dict, cancellation: dict, key: str
    ) -> dict:
        """Restore a cancelled trade with one new active adjusted copy."""
        f, t = self.settings.fields, self.settings.technical_fields
        output_id = f["output_id"]["column"]
        original_id = str(original[output_id])
        cancellation_id = str(cancellation[output_id])
        restored = deepcopy(original)
        restored[output_id] = f"ADJ-{key}"
        restored[t["record_type"]] = self.settings.record_types["adjusted"]
        restored[t["adjustment_reference"]] = key
        restored[t["source_output_id"]] = original_id
        restored[t["parent_output_id"]] = cancellation_id
        return restored
