"""Facts builder: every number Agent 4 may say is computed here, by code (SPEC A3)."""

from datetime import date
from typing import Any

from app.pipeline.schemas import ResolvedFilters, ToolResult

TOOL_PREFIX = {"get_cutting_summary": "cutting", "get_sales_summary": "sales", "get_stock_summary": "stock"}
SUMMABLE = ("sheets_cut", "reels_used", "weight_kg", "quantity_sheets", "invoice_count", "amount_pkr", "reels")
GROUP_LABELS = {"paper_type": "paper_type_name", "customer": "customer_name", "warehouse": "warehouse_name"}


def build_facts(results: list[ToolResult], rf: ResolvedFilters, ream_size: int) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for r in results:
        prefix = TOOL_PREFIX[r.tool]
        totals: dict[str, float] = {}
        for row in r.rows:
            for k in SUMMABLE:
                v = row.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    totals[k] = round(totals.get(k, 0) + v, 2)
        for k, v in totals.items():
            facts[f"{prefix}_total_{k}"] = int(v) if float(v).is_integer() else v
        if rf.quantity_unit == "ream":
            for k in ("sheets_cut", "quantity_sheets"):
                if k in totals:
                    facts[f"{prefix}_total_{k}_in_reams"] = round(totals[k] / ream_size, 1)
        if rf.quantity_unit == "ton" and "weight_kg" in totals:
            facts[f"{prefix}_total_weight_tons"] = round(totals["weight_kg"] / 1000, 2)
        if r.rows and rf.group_by:
            facts[f"{prefix}_group_count"] = len(r.rows)
    return facts


def fmt_date(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def date_label(rf: ResolvedFilters, today: date, language: str) -> str:
    ur = language == "roman_urdu"
    if rf.date_from == rf.date_to:
        word = None
        if rf.date_from == today:
            word = "Aaj" if ur else "Today"
        elif (today - rf.date_from).days == 1:
            word = "Kal" if ur else "Yesterday"
        return f"{word} ({fmt_date(rf.date_from)})" if word else fmt_date(rf.date_from)
    return f"{fmt_date(rf.date_from)} – {fmt_date(rf.date_to)}"


def filter_chips(rf: ResolvedFilters, tools: list[str]) -> dict[str, str]:
    only_stock = tools == ["get_stock_summary"]
    if only_stock:
        chips = {"Stock as of": fmt_date(rf.date_to)}
    elif rf.date_from == rf.date_to:
        chips = {"Date": fmt_date(rf.date_from)}
    else:
        chips = {"Date": f"{fmt_date(rf.date_from)} – {fmt_date(rf.date_to)}"}
    chips["Paper"] = rf.paper_type_name or "All"
    if rf.gsm:
        chips["GSM"] = str(rf.gsm)
    chips["Size"] = rf.size or "All"
    if rf.customer_name:
        chips["Customer"] = rf.customer_name
    if rf.warehouse_name:
        chips["Warehouse"] = rf.warehouse_name
    return chips


COLUMN_LABELS = {
    "date": "Date", "paper_type_name": "Paper", "gsm": "GSM", "size": "Size", "customer_name": "Customer",
    "warehouse_name": "Warehouse", "form": "Form", "sheets_cut": "Sheets cut", "reels_used": "Reels",
    "weight_kg": "Weight (kg)", "quantity_sheets": "Sheets", "invoice_count": "Invoices",
    "amount_pkr": "Amount (PKR)", "reels": "Reels",
}
HIDDEN_COLUMNS = {"paper_type", "customer", "warehouse"}  # codes; names are shown instead


def build_table(results: list[ToolResult], rf: ResolvedFilters) -> dict[str, Any] | None:
    if not rf.group_by:
        return None
    for r in results:
        if not r.rows:
            continue
        keys = [k for k in r.rows[0] if k not in HIDDEN_COLUMNS]
        if all(row.get("amount_pkr") is None for row in r.rows):
            keys = [k for k in keys if k != "amount_pkr"]
        return {
            "title": TOOL_PREFIX[r.tool].capitalize(),
            "columns": [COLUMN_LABELS.get(k, k) for k in keys],
            "rows": [[row.get(k) for k in keys] for row in r.rows[:50]],
        }
    return None
