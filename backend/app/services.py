from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
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


def row_version(row: dict[str, Any]) -> str:
    stable = {k: v for k, v in row.items() if not k.startswith("adjustment")}
    return sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


class DependencyResolver:
    def resolve(self, fields: set[str]) -> list[str]:
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
    def __init__(self, repository):
        self.repo = repository
        self.resolver = DependencyResolver()
        self.calc = MockCalculationAdapter()

    def _build(self, context, row_id, changes):
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
        replacement = deepcopy(current)
        replacement.update(actual)
        stages = self.resolver.resolve(set(actual))
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
        current = self.repo.get_effective_trade(request.context, request.rowId)
        cancellation = deepcopy(current)
        for field in ADDITIVE_MEASURES:
            if cancellation.get(field) is not None:
                cancellation[field] = -cancellation[field]
        cancellation["recordType"] = "ADJUSTMENT_CANCEL"
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
            "changedFields": changed,
            "impactedStages": [],
            "recalculatedFields": target["recalculatedFields"],
            "actionType": "REVERT",
            "revertedAdjustmentBatchId": batch_id,
        }
        return self.repo.commit_adjustment(
            built, request.reason, user, request.idempotencyKey
        )
