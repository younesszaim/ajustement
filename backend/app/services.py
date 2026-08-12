"""LiMon adjustment domain workflows.

The service is storage-agnostic. It builds immutable output rows, resolves the
smallest calculation path, validates optimistic concurrency and delegates
atomic/recoverable persistence to a repository. Preview calls the same builder
as commit but performs no writes.
"""

from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from uuid import UUID
from .config import (
    ADDITIVE_MEASURES,
    EDITABLE_FIELDS,
    FIELD_DEPENDENCIES,
    STAGE_DEPENDENCIES,
)


class DomainError(Exception):
    pass


class ConflictError(DomainError):
    pass


class InfrastructureError(Exception):
    """Temporary output/metadata coordination failure safe for HTTP 503."""

    pass


def row_version(row: dict[str, Any]) -> str:
    """Return a deterministic optimistic-lock token for an effective row."""
    stable = {k: v for k, v in row.items() if not k.startswith("adjustment")}
    return sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


class DependencyResolver:
    def resolve(self, fields: set[str]) -> list[str]:
        """Expand changed fields to a topologically ordered calculation path.

        Example: ``{"amount"}`` seeds EUR and bucket stages, which then pull in
        LCR impacts through ``STAGE_DEPENDENCIES``.
        """
        seeds = set().union(*(FIELD_DEPENDENCIES.get(f, set()) for f in fields))
        affected = set(seeds)
        changed = True
        while changed:
            changed = False
            for stage, deps in STAGE_DEPENDENCIES.items():
                if stage not in affected and deps & affected:
                    affected.add(stage)
                    changed = True
        ordered = []
        remaining = set(affected)
        while remaining:
            ready = sorted(
                s for s in remaining if not (STAGE_DEPENDENCIES[s] & remaining)
            )
            if not ready:
                raise DomainError("Calculation dependency cycle detected.")
            ordered.extend(ready)
            remaining -= set(ready)
        return ordered


class MockCalculationAdapter:
    """Deterministic demo only. Replace with the production LiMon Python adapter."""

    def recalculate(
        self, row: dict[str, Any], stages: list[str]
    ) -> tuple[dict[str, Any], list[str]]:
        out = deepcopy(row)
        recalculated = []
        amount = Decimal(str(out["amount"]))
        if "eur_amount" in stages:
            # TODO: replace with LiMon production FX calculation.
            rate = Decimal("1") if out["currency"] == "EUR" else Decimal("0.92")
            out["eurAmount0d"] = float(amount * rate)
            recalculated += ["eurAmount0d"]
        if "buckets" in stages:
            maturity = datetime.fromisoformat(out["maturityDate"]).date()
            base = datetime.fromisoformat(out["asofdate"]).date()
            days = (maturity - base).days
            for key in ["eurAmount7d", "eurAmount30d", "eurAmount3m"]:
                out[key] = 0.0
            bucket = (
                "eurAmount7d"
                if days <= 7
                else "eurAmount30d"
                if days <= 30
                else "eurAmount3m"
            )
            out[bucket] = float(amount)
            recalculated += ["eurAmount7d", "eurAmount30d", "eurAmount3m"]
        if "exposure_class" in stages:
            out["exposureClass"] = "FINANCIAL"
            recalculated += ["exposureClass"]
        if "hqla" in stages:
            out["hqlaLevel"] = (
                "L1" if out["targetInstrumentType"] == "SECURITY" else "NON_HQLA"
            )
            recalculated += ["hqlaLevel"]
        if "reporting_lines" in stages:
            days = (
                datetime.fromisoformat(out["maturityDate"]).date()
                - datetime.fromisoformat(out["asofdate"]).date()
            ).days
            out["reportingLineLcr"] = "RL_SEC_01" if days <= 30 else "RL_SEC_03"
            recalculated += ["reportingLineLcr"]
        if "lcr_impacts" in stages:
            out["lcrOutflow"] = float(amount * Decimal(".2"))
            recalculated += ["lcrOutflow", "lcrInflow"]
        return out, list(dict.fromkeys(recalculated))


class AdjustmentService:
    def __init__(self, repository, mapping_provider=None):
        self.repo = repository
        self.mappings = mapping_provider
        self.resolver = DependencyResolver()
        self.calc = MockCalculationAdapter()

    def _build(self, context, row_id, changes):
        """Build the authoritative preview journal for one standard adjustment.

        The result contains the current row, its additive negative reversal,
        the recalculated replacement, audit-friendly differences, and a row
        version used later by commit.
        """
        current = self.repo.get_effective_trade(context, row_id)
        illegal = set(changes) - EDITABLE_FIELDS
        if illegal:
            raise DomainError(
                f'Field "{sorted(illegal)[0]}" cannot be manually adjusted.'
            )
        actual = {k: v for k, v in changes.items() if current.get(k) != v}
        if not actual:
            raise DomainError("No values were changed.")
        if "amount" in actual:
            try:
                actual["amount"] = float(Decimal(str(actual["amount"])))
            except Exception as exc:
                raise DomainError("Amount must be numeric.") from exc
        mapping_overrides = (
            self.mappings.validate_overrides(actual) if self.mappings else []
        )
        replacement = deepcopy(current)
        replacement.update(actual)
        stages = self.resolver.resolve(set(actual))
        protected_producers = {
            override["producerStage"] for override in mapping_overrides
        }
        stages = [stage for stage in stages if stage not in protected_producers]
        replacement, recalculated = self.calc.recalculate(replacement, stages)
        cancellation = deepcopy(current)
        for field in ADDITIVE_MEASURES:
            if cancellation.get(field) is not None:
                cancellation[field] = -cancellation[field]
        cancellation["recordType"] = "ADJUSTMENT_CANCEL"
        replacement["recordType"] = "ADJUSTMENT_REPLACEMENT"
        changes_list = [
            {
                "field": k,
                "label": self._label(k),
                "oldValue": current.get(k),
                "newValue": v,
            }
            for k, v in actual.items()
        ]
        diffs = []
        for k in recalculated:
            if current.get(k) != replacement.get(k):
                a, b = current.get(k), replacement.get(k)
                delta = (
                    (b - a)
                    if isinstance(a, (int, float)) and isinstance(b, (int, float))
                    else None
                )
                diffs.append(
                    {
                        "field": k,
                        "label": self._label(k),
                        "current": a,
                        "recalculated": b,
                        "delta": delta,
                    }
                )
        return {
            "original": current,
            "cancellation": cancellation,
            "replacement": replacement,
            "changedFields": changes_list,
            "impactedStages": stages,
            "recalculatedFields": recalculated,
            "differences": diffs,
            "rowVersion": row_version(current),
            "context": context,
            "mappingOverrides": mapping_overrides,
        }

    @staticmethod
    def _label(k):
        return {
            "amount": "Amount",
            "maturityDate": "Maturity date",
            "targetInstrumentType": "Instrument type",
            "reportingLineLcr": "Reporting Line LCR",
            "eurAmount30d": "EUR Amount 30D",
            "eurAmount3m": "EUR Amount 3M",
            "lcrOutflow": "LCR Outflow",
        }.get(k, k.replace("_", " ").title())

    def preview(self, context, row_id, changes):
        return self._build(context, row_id, changes)

    @staticmethod
    def _cancel_row(current):
        cancellation = deepcopy(current)
        for field in ADDITIVE_MEASURES:
            if cancellation.get(field) is not None:
                cancellation[field] = -cancellation[field]
        cancellation["recordType"] = "ADJUSTMENT_CANCEL"
        return cancellation

    def preview_cancellation(self, context, row_id):
        """Build the single reversal used to cancel all active trade effect."""
        current = self.repo.get_effective_trade(context, row_id)
        cancellation = self._cancel_row(current)
        return {
            "operationType": "TRADE_CANCELLATION",
            "original": current,
            "cancellation": cancellation,
            "replacement": None,
            "outputRows": [cancellation],
            "changedFields": [
                {
                    "field": "businessEffect",
                    "label": "Business effect",
                    "oldValue": "ACTIVE",
                    "newValue": "CANCELLED",
                }
            ],
            "impactedStages": [],
            "recalculatedFields": [],
            "differences": [],
            "rowVersion": row_version(current),
            "context": context,
            "actionType": "TRADE_CANCELLATION",
        }

    def commit_cancellation(self, request, user):
        existing = self.repo.get_idempotent(request.idempotencyKey)
        if existing:
            return existing
        current = self.repo.get_effective_trade(request.context, request.rowId)
        if row_version(current) != request.expectedVersion:
            raise ConflictError(
                "The trade changed after cancellation preview. Refresh and preview again."
            )
        built = self.preview_cancellation(request.context, request.rowId)
        return self.repo.commit_adjustment(
            built, request.reason, user, request.idempotencyKey
        )

    @staticmethod
    def _proxy_trade_no(context, draft_id):
        try:
            suffix = UUID(draft_id).hex[:8].upper()
        except ValueError as exc:
            raise DomainError("The proxy draft identifier is invalid.") from exc
        return f"PROXY-{context.asofdate:%Y%m%d}-{suffix}"

    def preview_proxy(self, context, draft_id, fields):
        values = fields.model_dump(mode="json")
        if values["amount"] == 0:
            raise DomainError("A proxy amount cannot be zero.")
        trade_no = self._proxy_trade_no(context, draft_id)
        proxy = {
            "rowId": trade_no,
            "tradeKey": "|".join(
                [values["foSystem"], trade_no, values.get("isin") or "", values["portfolio"]]
            ),
            "tradeNo": trade_no,
            **values,
            "asofdate": context.asofdate.isoformat(),
            "recordType": "PROXY",
            "eurAmount0d": 0.0,
            "eurAmount7d": 0.0,
            "eurAmount30d": 0.0,
            "eurAmount3m": 0.0,
            "lcrInflow": 0.0,
            "lcrOutflow": 0.0,
            "reserve": 0.0,
            "exposureClass": "",
            "hqlaLevel": "",
            "reportingLineLcr": "",
            "_outputRecordId": None,
        }
        stages = self.resolver.resolve(set(values))
        proxy, recalculated = self.calc.recalculate(proxy, stages)
        return {
            "operationType": "PROXY",
            "original": None,
            "cancellation": None,
            "replacement": proxy,
            "outputRows": [proxy],
            "changedFields": [
                {
                    "field": key,
                    "label": self._label(key),
                    "oldValue": None,
                    "newValue": value,
                }
                for key, value in values.items()
            ],
            "impactedStages": stages,
            "recalculatedFields": recalculated,
            "differences": [],
            "rowVersion": row_version(proxy),
            "context": context,
            "actionType": "PROXY",
        }

    def commit_proxy(self, request, user):
        existing = self.repo.get_idempotent(request.idempotencyKey)
        if existing:
            return existing
        built = self.preview_proxy(request.context, request.draftId, request.fields)
        return self.repo.commit_adjustment(
            built, request.reason, user, request.idempotencyKey
        )

    def commit(self, request, user):
        existing = self.repo.get_idempotent(request.idempotencyKey)
        if existing:
            return existing
        authoritative = self.repo.get_effective_trade(request.context, request.rowId)
        if row_version(authoritative) != request.expectedVersion:
            raise ConflictError(
                "The trade changed after your preview. Refresh the trade and generate a new preview."
            )
        built = self._build(request.context, request.rowId, request.changes)
        return self.repo.commit_adjustment(
            built, request.reason, user, request.idempotencyKey
        )

    def commit_batch(self, request, user):
        existing = self.repo.get_idempotent(request.idempotencyKey)
        if existing:
            return existing
        row_ids = [item.rowId for item in request.items]
        if len(row_ids) != len(set(row_ids)):
            raise DomainError("A trade can appear only once in an adjustment batch.")
        built = []
        for item in request.items:
            current = self.repo.get_effective_trade(request.context, item.rowId)
            if row_version(current) != item.expectedVersion:
                raise ConflictError(
                    f"Trade {current['tradeNo']} changed after preview. Refresh and preview the batch again."
                )
            built.append(self._build(request.context, item.rowId, item.changes))
        return self.repo.commit_adjustment_batch(
            built, request.reason, user, request.idempotencyKey
        )

    def preview_batch(self, context, items):
        row_ids = [item.rowId for item in items]
        if len(row_ids) != len(set(row_ids)):
            raise DomainError("A trade can appear only once in an adjustment batch.")
        previews = [self._build(context, item.rowId, item.changes) for item in items]
        stages = list(
            dict.fromkeys(
                stage for preview in previews for stage in preview["impactedStages"]
            )
        )
        recalculated = list(
            dict.fromkeys(
                field for preview in previews for field in preview["recalculatedFields"]
            )
        )
        totals = {}
        for preview in previews:
            for difference in preview["differences"]:
                if difference.get("delta") is not None:
                    totals[difference["field"]] = (
                        totals.get(difference["field"], 0) + difference["delta"]
                    )
        return {
            "items": previews,
            "tradeCount": len(previews),
            "insertedRecords": len(previews) * 2,
            "impactedStages": stages,
            "recalculatedFields": recalculated,
            "aggregateDeltas": [
                {"field": field, "label": self._label(field), "delta": delta}
                for field, delta in totals.items()
            ],
        }

    def revert_adjustment(self, batch_id, request, user):
        existing = self.repo.get_idempotent(request.idempotencyKey)
        if existing:
            return existing
        target = self.repo.get_adjustment(request.rowId, batch_id, request.context)
        target_action = target.get("actionType", "ADJUSTMENT")
        if target_action == "TRADE_CANCELLATION":
            current = target["cancellation"]
            cancellation = None
            replacement = deepcopy(target["original"])
            replacement["recordType"] = "ADJUSTMENT_REPLACEMENT"
        elif target_action == "PROXY":
            current = self.repo.get_effective_trade(request.context, request.rowId)
            cancellation = self._cancel_row(current)
            replacement = None
        else:
            current = self.repo.get_effective_trade(request.context, request.rowId)
            cancellation = self._cancel_row(current)
            replacement = deepcopy(target["original"])
            replacement["recordType"] = "ADJUSTMENT_REPLACEMENT"
        changed = [
            {
                "field": x["field"],
                "label": x["label"],
                "oldValue": x["newValue"],
                "newValue": x["oldValue"],
            }
            for x in target["changedFields"]
        ]
        built = {
            "context": request.context,
            "original": current,
            "cancellation": cancellation,
            "replacement": replacement,
            "outputRows": [
                row for row in (cancellation, replacement) if row is not None
            ],
            "changedFields": changed,
            "impactedStages": [],
            "recalculatedFields": target["recalculatedFields"],
            "actionType": "REVERT",
            "revertedAdjustmentBatchId": batch_id,
        }
        return self.repo.commit_adjustment(
            built, request.reason, user, request.idempotencyKey
        )
