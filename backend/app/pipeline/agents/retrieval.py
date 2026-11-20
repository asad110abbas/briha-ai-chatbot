"""Agent 2 - Data Retrieval (SPEC §8). Deterministic: no LLM. Runs only catalogued tools."""

import asyncio
from typing import Any

from app.config import Settings
from app.datasources.base import DataSource, DataSourceError
from app.pipeline.schemas import ResolvedFilters, ToolResult

MAX_ROWS = 500
FINANCIAL_FIELDS = ("amount_pkr",)
TOOL_GROUP_BY = {
    "get_cutting_summary": {"date", "paper_type", "gsm", "size"},
    "get_sales_summary": {"date", "paper_type", "gsm", "size", "customer"},
    "get_stock_summary": {"paper_type", "gsm", "size", "warehouse", "form"},
}


def build_params(tool: str, rf: ResolvedFilters) -> dict[str, Any]:
    group_by = rf.group_by if rf.group_by in TOOL_GROUP_BY[tool] else None
    common = {"paper_type_code": rf.paper_type_code, "gsm": rf.gsm, "size": rf.size}
    if tool == "get_stock_summary":
        return {"as_of": rf.date_to, **common, "warehouse_code": rf.warehouse_code, "form": None,
                "group_by": group_by}
    params = {"date_from": rf.date_from, "date_to": rf.date_to, **common, "group_by": group_by}
    if tool == "get_sales_summary":
        params["customer_code"] = rf.customer_code
    return params


async def _run_one(ds: DataSource, tool: str, params: dict[str, Any], timeout: float) -> ToolResult:
    last: DataSourceError | None = None
    for _ in range(2):  # 1 retry on timeout / unavailable (SPEC R2)
        try:
            return await asyncio.wait_for(ds.run_tool(tool, params), timeout=timeout)
        except TimeoutError:
            last = DataSourceError("DATA_SOURCE_TIMEOUT", f"{tool} timed out")
        except DataSourceError as exc:
            last = exc
    assert last is not None
    raise last


async def retrieve(ds: DataSource, settings: Settings, tools: list[str], rf: ResolvedFilters,
                   can_view_financials: bool) -> list[ToolResult]:
    """Raises DataSourceError if any tool fails after retry (SPEC R8)."""
    calls = [_run_one(ds, tool, build_params(tool, rf), settings.tool_timeout_seconds) for tool in tools]
    results = list(await asyncio.gather(*calls))
    for r in results:
        if len(r.rows) > MAX_ROWS:
            r.rows, r.truncated = r.rows[:MAX_ROWS], True
        if not can_view_financials:
            for row in r.rows:
                for f in FINANCIAL_FIELDS:
                    if f in row:
                        row[f] = None
    return results
