from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from .services import DomainError

FLOW1 = "2026-08-07T04:45:02"
FLOW2 = "2026-08-07T11:14:09"


def trade(i, no, fo, amount, isin, instrument="SECURITY"):
    return {
        "rowId": f"ROW-{i:04}",
        "tradeKey": f"{fo}|{no}|{isin}",
        "tradeNo": no,
        "foSystem": fo,
        "targetInstrumentType": instrument,
        "isin": isin,
        "issue": "ISSUER_A",
        "valueDate": "2026-08-06",
        "maturityDate": "2026-08-20",
        "currency": "EUR",
        "amount": float(amount),
        "portfolio": "LIQUIDITY",
        "counterparty": "CP_BANK_01",
        "exposureClass": "FINANCIAL",
        "hqlaLevel": "L1",
        "reportingLineAble": "ABLE_01",
        "reportingLineLcr": "RL_SEC_01",
        "eurAmount0d": 0.0,
        "eurAmount7d": 0.0,
        "eurAmount30d": float(amount),
        "eurAmount3m": 0.0,
        "lcrInflow": 0.0,
        "lcrOutflow": float(amount) * 0.2,
        "reserve": 0.0,
        "recordType": "BASE",
        "asofdate": "2026-08-06",
    }


class MockRepository:
    def __init__(self):
        rows = [
            trade(1, "OT-982731", "Orchestrade", 1_000_000, "FR0012345678"),
            trade(2, "MX-441082", "Murex", 750_000, "DE000A1EWWW0"),
            trade(3, "KD-109221", "Kondor", 2_400_000, "GB00B03MLX29", "DEPOSIT"),
            trade(4, "SP-830114", "SOPHIS", 320_000, "US0378331005"),
            trade(5, "AP-230912", "APEX", 5_000_000, "FR0000120271"),
        ]
        self.data = {
            ("2026-08-06", FLOW1): deepcopy(rows),
            ("2026-08-06", FLOW2): deepcopy(rows),
            ("2026-08-05", "2026-08-06T06:12:00"): deepcopy(rows),
        }
        self.history = {}
        self.idempotency = {}
        self.sequence = 123
        self.lock = RLock()
        self._seed_history(rows[0])

    def _seed_history(self, current):
        original = deepcopy(current)
        original.update(
            {
                "amount": 900000.0,
                "maturityDate": "2026-08-15",
                "eurAmount30d": 900000.0,
                "lcrOutflow": 180000.0,
            }
        )
        cancellation = deepcopy(original)
        for field in [
            "amount",
            "eurAmount0d",
            "eurAmount7d",
            "eurAmount30d",
            "eurAmount3m",
            "lcrInflow",
            "lcrOutflow",
            "reserve",
        ]:
            cancellation[field] = -cancellation[field]
        cancellation["recordType"] = "ADJUSTMENT_CANCEL"
        replacement = deepcopy(current)
        replacement["recordType"] = "ADJUSTMENT_REPLACEMENT"
        self.history[current["rowId"]] = [
            {
                "adjustmentBatchId": "ADJ-20260807-000123",
                "status": "COMMITTED",
                "timestamp": "2026-08-07T14:32:18+00:00",
                "user": "finance.user@example",
                "reason": "Correction following confirmation from the Front Office.",
                "baseAsOfDate": "2026-08-06",
                "baseAsOfDateFlow": FLOW1,
                "changedFields": [
                    {
                        "field": "amount",
                        "label": "Amount",
                        "oldValue": 900000.0,
                        "newValue": 1000000.0,
                    },
                    {
                        "field": "maturityDate",
                        "label": "Maturity date",
                        "oldValue": "2026-08-15",
                        "newValue": "2026-08-20",
                    },
                ],
                "recalculatedFields": [
                    "eurAmount30d",
                    "reportingLineLcr",
                    "lcrOutflow",
                ],
                "original": original,
                "cancellation": cancellation,
                "replacement": replacement,
            }
        ]
        self.data[("2026-08-06", FLOW1)][0] = deepcopy(replacement)

    def asofdates(self):
        return sorted({k[0] for k in self.data}, reverse=True)

    def versions(self, date):
        return sorted([f for d, f in self.data if d == date], reverse=True)

    def _key(self, c):
        return (c.asofdate.isoformat(), c.asofdateflow.isoformat())

    def search(self, c, search, fo, page, page_size):
        effective = self.data.get(self._key(c), [])
        needle = search.lower()
        matches = [
            r
            for r in effective
            if (
                not needle
                or any(
                    needle in str(r.get(k, "")).lower()
                    for k in ["tradeNo", "isin", "rowId"]
                )
            )
            and (not fo or r["foSystem"] == fo)
        ]
        expanded = []
        for match in matches:
            lineage = self.get_lineage(c, match["rowId"])
            for associated in lineage["rows"]:
                row = deepcopy(associated["row"])
                row.update(
                    {
                        "isAdjusted": lineage["isAdjusted"],
                        "adjustmentCount": lineage["adjustmentCount"],
                        "activeRecordType": lineage["activeRow"]["recordType"],
                        "lineageRole": associated["role"],
                        "isActive": associated["isActive"],
                        "adjustmentBatchId": associated["adjustmentBatchId"],
                        "lineageTimestamp": associated["timestamp"],
                    }
                )
                expanded.append(row)
        start = (page - 1) * page_size
        return expanded[start : start + page_size], len(expanded)

    def get_effective_trade(self, c, row_id):
        row = next(
            (x for x in self.data.get(self._key(c), []) if x["rowId"] == row_id), None
        )
        if not row:
            raise DomainError("Trade not found in the selected LiMon version.")
        return deepcopy(row)

    def get_history(self, row_id):
        return deepcopy(self.history.get(row_id, []))

    def get_adjustment(self, row_id, batch_id, c):
        entries = [
            x
            for x in self.history.get(row_id, [])
            if x["baseAsOfDate"] == c.asofdate.isoformat()
            and x["baseAsOfDateFlow"] == c.asofdateflow.isoformat()
        ]
        target = next((x for x in entries if x["adjustmentBatchId"] == batch_id), None)
        if not target:
            raise DomainError("Adjustment not found for this trade and LiMon version.")
        if not entries or entries[0]["adjustmentBatchId"] != batch_id:
            raise DomainError(
                "Only the latest active adjustment can be reverted. Revert newer adjustments first."
            )
        if target.get("actionType") == "REVERT":
            raise DomainError(
                "A revert record cannot be reverted as a deletion action."
            )
        return deepcopy(target)

    def get_lineage(self, c, row_id):
        current = self.get_effective_trade(c, row_id)
        entries = [
            x
            for x in self.history.get(row_id, [])
            if x["baseAsOfDate"] == c.asofdate.isoformat()
            and x["baseAsOfDateFlow"] == c.asofdateflow.isoformat()
        ]
        if not entries:
            return {
                "isAdjusted": False,
                "adjustmentCount": 0,
                "activeRow": current,
                "rows": [
                    {
                        "role": "ORIGINAL",
                        "isActive": True,
                        "adjustmentBatchId": None,
                        "timestamp": None,
                        "row": current,
                    }
                ],
            }
        chronological = sorted(entries, key=lambda x: x["timestamp"])
        rows = [
            {
                "role": "ORIGINAL",
                "isActive": False,
                "adjustmentBatchId": None,
                "timestamp": None,
                "row": chronological[0]["original"],
            }
        ]
        for entry in chronological:
            rows.extend(
                [
                    {
                        "role": "REVERSAL",
                        "isActive": False,
                        "adjustmentBatchId": entry["adjustmentBatchId"],
                        "timestamp": entry["timestamp"],
                        "row": entry["cancellation"],
                    },
                    {
                        "role": "ADJUSTED",
                        "isActive": False,
                        "adjustmentBatchId": entry["adjustmentBatchId"],
                        "timestamp": entry["timestamp"],
                        "row": entry["replacement"],
                    },
                ]
            )
        rows[-1]["isActive"] = True
        return {
            "isAdjusted": True,
            "adjustmentCount": len(entries),
            "activeRow": current,
            "rows": rows,
        }

    def get_global_history(self, asofdate="", asofdateflow=""):
        items = [item for entries in self.history.values() for item in entries]
        if asofdate:
            items = [x for x in items if x["baseAsOfDate"] == asofdate]
        if asofdateflow:
            items = [x for x in items if x["baseAsOfDateFlow"] == asofdateflow]
        return deepcopy(sorted(items, key=lambda x: x["timestamp"], reverse=True))

    def get_idempotent(self, key):
        return deepcopy(self.idempotency.get(key))

    def commit_adjustment(self, built, reason, user, key):
        return self.commit_adjustment_batch([built], reason, user, key)

    def commit_adjustment_batch(self, built_items, reason, user, key):
        with self.lock:
            if key in self.idempotency:
                return deepcopy(self.idempotency[key])
            self.sequence += 1
            batch = f"ADJ-{datetime.now(timezone.utc):%Y%m%d}-{self.sequence:06d}"
            now = datetime.now(timezone.utc).isoformat()
            prepared = []
            for built in built_items:
                cancel = deepcopy(built["cancellation"])
                replacement = deepcopy(built["replacement"])
                for row in (cancel, replacement):
                    row.update(
                        {
                            "adjustmentBatchId": batch,
                            "adjustmentTimestamp": now,
                            "adjustmentUser": user,
                            "adjustmentReason": reason,
                            "originalRowId": built["original"]["rowId"],
                        }
                    )
                context = built["context"]
                prepared.append(
                    (
                        built,
                        replacement,
                        {
                            "adjustmentBatchId": batch,
                            "status": "COMMITTED",
                            "actionType": built.get("actionType", "ADJUSTMENT"),
                            "revertedAdjustmentBatchId": built.get(
                                "revertedAdjustmentBatchId"
                            ),
                            "insertedRecords": 2,
                            "timestamp": now,
                            "user": user,
                            "reason": reason,
                            "baseAsOfDate": context.asofdate.isoformat(),
                            "baseAsOfDateFlow": context.asofdateflow.isoformat(),
                            "changedFields": built["changedFields"],
                            "recalculatedFields": built["recalculatedFields"],
                            "original": deepcopy(built["original"]),
                            "cancellation": cancel,
                            "replacement": replacement,
                        },
                    )
                )
            # All records are prepared before any effective state or audit history is mutated.
            for built, replacement, item in prepared:
                rows = self.data[self._key(built["context"])]
                for i, row in enumerate(rows):
                    if row["rowId"] == built["original"]["rowId"]:
                        rows[i] = deepcopy(replacement)
                self.history.setdefault(built["original"]["rowId"], []).insert(0, item)
            result = {
                "adjustmentBatchId": batch,
                "status": "COMMITTED",
                "insertedRecords": 2 * len(prepared),
                "adjustedTrades": len(prepared),
            }
            self.idempotency[key] = result
            return deepcopy(result)
