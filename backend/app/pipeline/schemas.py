"""Typed contracts of the pipeline (SPEC §4, §7.4, §9)."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

Language = Literal["english", "roman_urdu"]
Intent = Literal["data_query", "clarification_needed", "help", "conversation", "out_of_scope", "write_request"]
Metric = Literal[
    "sheets_cut", "reels_used", "weight_cut_kg",
    "quantity_sold", "weight_sold_kg", "invoice_count", "amount_sold_pkr",
    "stock_sheets", "stock_reels", "stock_weight_kg",
]
DateExpression = Literal[
    "today", "yesterday", "day_before_yesterday", "this_week", "last_week", "this_month",
    "last_month", "this_year", "last_n_days", "specific_date", "date_range", "none",
]
ToolName = Literal["get_cutting_summary", "get_sales_summary", "get_stock_summary"]
GroupBy = Literal["date", "paper_type", "gsm", "size", "customer", "warehouse", "form"]
Unit = Literal["sheet", "ream", "kg", "ton"]
Status = Literal["answered", "clarification", "no_data", "refused", "error"]

TOOLS: tuple[str, ...] = ("get_cutting_summary", "get_sales_summary", "get_stock_summary")


# ---- Agent 1 output -------------------------------------------------------------------------
class DateFilter(BaseModel):
    expression: DateExpression
    n: int | None
    from_date: str | None
    to_date: str | None


class Filters(BaseModel):
    date: DateFilter
    paper_type: str | None
    gsm: int | None
    size: str | None
    customer: str | None
    warehouse: str | None


class Clarification(BaseModel):
    question: str
    options: list[str]


class QueryPlan(BaseModel):
    language: Language
    reply_language: Language | None  # only when the user asks which language BRIHA should answer in
    intent: Intent
    metrics: list[Metric]
    filters: Filters
    quantity_unit: Unit | None
    group_by: GroupBy | None
    tool_calls: list[ToolName]
    clarification: Clarification | None
    assumptions: list[str]
    confidence: float


# ---- Agent 3 output -------------------------------------------------------------------------
class JudgeVerdict(BaseModel):
    verdict: Literal["pass", "fail"]
    issue: Literal["wrong_metric", "wrong_date", "wrong_filter", "wrong_tool", "incomplete", "other"] | None
    explanation: str
    fix_hint: str | None


# ---- Resolved filters (after code resolution) -----------------------------------------------
class ResolvedFilters(BaseModel):
    date_from: date
    date_to: date
    paper_type_code: str | None = None
    paper_type_name: str | None = None
    gsm: int | None = None
    size: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    group_by: GroupBy | None = None
    quantity_unit: Unit | None = None


# ---- Agent 2 output -------------------------------------------------------------------------
class ToolResult(BaseModel):
    tool: str
    ok: bool
    params: dict[str, Any] = {}
    applied_filters: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    truncated: bool = False
    source_ref: str = ""
    duration_ms: int = 0
    error: str | None = None
