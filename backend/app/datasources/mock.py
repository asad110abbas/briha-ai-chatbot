"""Mock company data (SPEC §7, Schema §3): ~180 days of deterministic, realistic cutting/sales/stock.

Used for development, demos and tests until a real company REST API is connected.
Fault injection (MOCK_FAULTS or .faults): down, timeout, wrong_dates, empty.
"""

import asyncio
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.datasources.base import DataSourceError, MasterData, iso
from app.pipeline.resolve.entities import MasterItem
from app.pipeline.schemas import ToolResult

PAPER_TYPES: dict[str, tuple[str, list[int]]] = {
    "ART_PAPER": ("Art Paper", [90, 100, 128, 150]),
    "ART_CARD": ("Art Card", [210, 250, 300]),
    "BLEACH_CARD": ("Bleach Card", [230, 250, 300, 350]),
    "OFFSET": ("Offset Paper", [60, 70, 80, 100]),
    "DUPLEX": ("Duplex Board", [250, 300, 350, 400]),
    "KRAFT": ("Kraft Paper", [80, 100, 125]),
    "NEWSPRINT": ("Newsprint", [45, 48]),
}
SIZES = ["18x23", "20x30", "22x28", "23x36", "25x36", "25x38", "27x39", "30x40"]
CUSTOMERS = {
    "C001": "Northwind Printers", "C002": "Bluebird Packaging", "C003": "Maple Offset Press",
    "C004": "Cedar Box Makers", "C005": "Harbor Stationers", "C006": "Summit Publishers",
}
WAREHOUSES = {"MAIN": "Main Godown", "CITY": "City Warehouse"}
HISTORY_DAYS = 180


def _weight_kg(sheets: int, size: str, gsm: int) -> float:
    w, l = (float(x) for x in size.split("x"))
    return round(sheets * (w * 0.0254) * (l * 0.0254) * gsm / 1000, 2)


@dataclass
class _Data:
    built_for: date
    cutting: list[dict[str, Any]]
    sales: list[dict[str, Any]]


class MockDataSource:
    mode = "mock"

    def __init__(self, today_fn, faults: str = ""):
        self._today_fn = today_fn
        self.faults: set[str] = {f.strip() for f in faults.split(",") if f.strip()}
        self._data: _Data | None = None

    # ---- data generation -----------------------------------------------------------------
    def _build(self, today: date) -> _Data:
        rnd = random.Random(42)
        codes = list(PAPER_TYPES)
        cutting, sales = [], []
        start = today - timedelta(days=HISTORY_DAYS)
        reel_no = 1000
        for offset in range(HISTORY_DAYS + 1):
            d = start + timedelta(days=offset)
            if d.weekday() == 6:  # Sunday off
                continue
            for _ in range(rnd.randint(3, 8)):
                code = rnd.choice(codes)
                gsm = rnd.choice(PAPER_TYPES[code][1])
                size = rnd.choice(SIZES)
                sheets = rnd.randint(5, 60) * 100
                reel_no += 1
                cutting.append({"date": d, "paper_type": code, "gsm": gsm, "size": size, "sheets": sheets,
                                "reel_id": f"R{reel_no}", "weight_kg": _weight_kg(sheets, size, gsm)})
            for inv in range(rnd.randint(3, 10)):
                code = rnd.choice(codes)
                gsm = rnd.choice(PAPER_TYPES[code][1])
                size = rnd.choice(SIZES)
                sheets = rnd.randint(2, 40) * 100
                rate = rnd.choice([18, 22, 26, 35, 48, 60])
                sales.append({"date": d, "invoice": f"INV-{d:%y%m%d}-{inv}", "customer": rnd.choice(list(CUSTOMERS)),
                              "paper_type": code, "gsm": gsm, "size": size, "sheets": sheets,
                              "weight_kg": _weight_kg(sheets, size, gsm), "amount_pkr": float(sheets * rate)})
        return _Data(today, cutting, sales)

    def _get(self) -> _Data:
        today = self._today_fn()
        if self._data is None or self._data.built_for != today:
            self._data = self._build(today)
        return self._data

    # ---- interface -----------------------------------------------------------------------
    async def health(self) -> bool:
        return "down" not in self.faults

    async def master_data(self) -> MasterData:
        return MasterData(
            paper_types=[MasterItem(c, n) for c, (n, _) in PAPER_TYPES.items()],
            customers=[MasterItem(c, n) for c, n in CUSTOMERS.items()],
            warehouses=[MasterItem(c, n) for c, n in WAREHOUSES.items()],
        )

    async def run_tool(self, tool: str, params: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        if "down" in self.faults:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", "mock fault: down")
        if "timeout" in self.faults:
            await asyncio.sleep(3600)
        applied = dict(params)
        effective = dict(params)
        if "wrong_dates" in self.faults:  # simulate a buggy API that ignores the date filter
            for k in ("date_from", "date_to", "as_of"):
                if effective.get(k):
                    effective[k] = effective[k] - timedelta(days=30)
                    applied[k] = effective[k]
        if tool == "get_cutting_summary":
            rows = self._summary(self._get().cutting, effective, {"sheets_cut": "sheets", "weight_kg": "weight_kg"},
                                 reels=True)
        elif tool == "get_sales_summary":
            rows = self._summary(self._get().sales, effective,
                                 {"quantity_sheets": "sheets", "weight_kg": "weight_kg", "amount_pkr": "amount_pkr"},
                                 invoices=True)
        elif tool == "get_stock_summary":
            rows = self._stock(effective)
        else:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"unknown tool {tool}")
        if "empty" in self.faults:
            rows = []
        return ToolResult(
            tool=tool, ok=True, params={k: iso(v) for k, v in params.items()},
            applied_filters={k: iso(v) for k, v in applied.items()},
            rows=rows, row_count=len(rows), source_ref=f"mock:{tool}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # ---- aggregation ---------------------------------------------------------------------
    @staticmethod
    def _match(r: dict[str, Any], p: dict[str, Any]) -> bool:
        return (
            p["date_from"] <= r["date"] <= p["date_to"]
            and (p.get("paper_type_code") is None or r["paper_type"] == p["paper_type_code"])
            and (p.get("gsm") is None or r["gsm"] == p["gsm"])
            and (p.get("size") is None or r["size"] == p["size"])
            and (p.get("customer_code") is None or r.get("customer") == p["customer_code"])
        )

    @staticmethod
    def _group_key(r: dict[str, Any], group_by: str | None) -> dict[str, Any]:
        match group_by:
            case "date":
                return {"date": r["date"].isoformat()}
            case "paper_type":
                return {"paper_type": r["paper_type"], "paper_type_name": PAPER_TYPES[r["paper_type"]][0]}
            case "gsm":
                return {"gsm": r["gsm"]}
            case "size":
                return {"size": r["size"]}
            case "customer":
                return {"customer": r["customer"], "customer_name": CUSTOMERS[r["customer"]]}
            case _:
                return {}

    def _summary(self, data, p, fields: dict[str, str], reels=False, invoices=False) -> list[dict[str, Any]]:
        groups: dict[tuple, dict[str, Any]] = {}
        reel_sets: dict[tuple, set] = defaultdict(set)
        invoice_sets: dict[tuple, set] = defaultdict(set)
        for r in data:
            if not self._match(r, p):
                continue
            key_fields = self._group_key(r, p.get("group_by"))
            key = tuple(key_fields.items())
            g = groups.setdefault(key, {**key_fields, **{out: 0 for out in fields}})
            for out, src in fields.items():
                g[out] = round(g[out] + r[src], 2)
            if reels:
                reel_sets[key].add(r["reel_id"])
            if invoices:
                invoice_sets[key].add(r["invoice"])
        rows = []
        for key, g in groups.items():
            if reels:
                g["reels_used"] = len(reel_sets[key])
            if invoices:
                g["invoice_count"] = len(invoice_sets[key])
            rows.append(g)
        if p.get("group_by"):
            rows.sort(key=lambda x: str(next(iter(x.values()))))
        return rows

    def _stock(self, p: dict[str, Any]) -> list[dict[str, Any]]:
        as_of: date = p["as_of"]
        groups: dict[tuple, dict[str, Any]] = {}
        for code, (name, gsms) in PAPER_TYPES.items():
            if p.get("paper_type_code") not in (None, code):
                continue
            for gsm in gsms:
                if p.get("gsm") not in (None, gsm):
                    continue
                for wh in WAREHOUSES:
                    if p.get("warehouse_code") not in (None, wh):
                        continue
                    for form, size in [("reel", None)] + [("sheet", s) for s in SIZES]:
                        if p.get("form") not in (None, form):
                            continue
                        if p.get("size") is not None and size != p["size"]:
                            continue
                        rnd = random.Random(f"{code}{gsm}{wh}{size}{as_of.toordinal()}")
                        g_key = self._stock_key(p.get("group_by"), code, name, gsm, size, wh, form)
                        key = tuple(g_key.items())
                        g = groups.setdefault(key, {**g_key, "quantity_sheets": 0, "reels": 0, "weight_kg": 0.0})
                        if form == "reel":
                            reels = rnd.randint(0, 12)
                            g["reels"] += reels
                            g["weight_kg"] = round(g["weight_kg"] + reels * rnd.randint(400, 900), 2)
                        else:
                            sheets = rnd.randint(0, 80) * 100
                            g["quantity_sheets"] += sheets
                            g["weight_kg"] = round(g["weight_kg"] + _weight_kg(sheets, size, gsm), 2)
        return list(groups.values())

    @staticmethod
    def _stock_key(group_by, code, name, gsm, size, wh, form) -> dict[str, Any]:
        match group_by:
            case "paper_type":
                return {"paper_type": code, "paper_type_name": name}
            case "gsm":
                return {"gsm": gsm}
            case "size":
                return {"size": size or "REEL"}
            case "warehouse":
                return {"warehouse": wh, "warehouse_name": WAREHOUSES[wh]}
            case "form":
                return {"form": form}
            case _:
                return {}
