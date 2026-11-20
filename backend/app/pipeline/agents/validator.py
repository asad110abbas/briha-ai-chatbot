"""Agent 3 - Result Validation Guard (SPEC §9): deterministic checks V1-V6, then an LLM judge."""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.config import Settings
from app.llm.client import LLM, Usage
from app.pipeline.agents.understanding import load_prompt
from app.pipeline.schemas import JudgeVerdict, QueryPlan, ResolvedFilters, ToolResult

# metric -> (tool that provides it, row field)
METRIC_FIELDS: dict[str, tuple[str, str]] = {
    "sheets_cut": ("get_cutting_summary", "sheets_cut"),
    "reels_used": ("get_cutting_summary", "reels_used"),
    "weight_cut_kg": ("get_cutting_summary", "weight_kg"),
    "quantity_sold": ("get_sales_summary", "quantity_sheets"),
    "weight_sold_kg": ("get_sales_summary", "weight_kg"),
    "invoice_count": ("get_sales_summary", "invoice_count"),
    "amount_sold_pkr": ("get_sales_summary", "amount_pkr"),
    "stock_sheets": ("get_stock_summary", "quantity_sheets"),
    "stock_reels": ("get_stock_summary", "reels"),
    "stock_weight_kg": ("get_stock_summary", "weight_kg"),
}
SHEET_FIELDS = ("sheets_cut", "quantity_sheets")


@dataclass
class Validation:
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    valid_zero: bool = False
    llm_verdict: str | None = None
    issue: str | None = None
    fix_hint: str | None = None
    usage: Usage = field(default_factory=Usage)

    def as_json(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks, "valid_zero": self.valid_zero,
                "llm_verdict": self.llm_verdict, "issue": self.issue, "fix_hint": self.fix_hint}


def deterministic_checks(plan: QueryPlan, rf: ResolvedFilters, results: list[ToolResult],
                         settings: Settings) -> Validation:
    checks: list[dict[str, Any]] = []
    hints: list[str] = []

    def add(cid: str, ok: bool, msg: str = "") -> None:
        checks.append({"id": cid, "pass": ok, **({"message": msg} if msg else {})})
        if not ok and msg:
            hints.append(msg)

    by_tool = {r.tool: r for r in results}

    # V1 every planned tool ran ok
    missing = [t for t in plan.tool_calls if t not in by_tool or not by_tool[t].ok]
    add("V1", not missing, f"tools failed or missing: {missing}" if missing else "")

    # V2 applied filters equal what we asked for
    mismatches = []
    for r in results:
        for k, v in r.params.items():
            if v is not None and k != "group_by" and str(r.applied_filters.get(k)) != str(v):
                mismatches.append(f"{r.tool}.{k}: asked {v}, source applied {r.applied_filters.get(k)}")
    add("V2", not mismatches, "; ".join(mismatches))

    # V3 row dates within range
    bad_dates = []
    for r in results:
        for row in r.rows:
            if "date" in row and not (rf.date_from <= date.fromisoformat(str(row["date"])[:10]) <= rf.date_to):
                bad_dates.append(f"{r.tool} row date {row['date']} outside {rf.date_from}..{rf.date_to}")
                break
    add("V3", not bad_dates, "; ".join(bad_dates))

    # V4 requested metrics are covered by a called tool and present in rows (only if there are rows)
    metric_problems = []
    for m in plan.metrics:
        tool, fld = METRIC_FIELDS[m]
        if tool not in by_tool:
            metric_problems.append(f"metric {m} needs tool {tool}, which was not called")
        elif by_tool[tool].row_count > 0 and fld not in by_tool[tool].rows[0]:
            metric_problems.append(f"metric {m}: field {fld} missing in {tool} rows")
    add("V4", not metric_problems, "; ".join(metric_problems))

    # V5 sanity
    days = (rf.date_to - rf.date_from).days + 1
    limit = settings.sanity_max_sheets_per_day * days
    insane = []
    for r in results:
        for row in r.rows:
            for k, v in row.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if v < 0:
                        insane.append(f"{r.tool}.{k} negative ({v})")
                    elif k in SHEET_FIELDS and v > limit:
                        insane.append(f"{r.tool}.{k}={v} above sanity limit")
    add("V5", not insane, "; ".join(insane[:3]))

    passed = all(c["pass"] for c in checks)
    # V6 valid zero: correct query, nothing recorded
    valid_zero = passed and bool(results) and all(r.row_count == 0 for r in results)
    checks.append({"id": "V6", "pass": True, "valid_zero": valid_zero})
    return Validation(passed=passed, checks=checks, valid_zero=valid_zero, fix_hint="; ".join(hints) or None,
                      issue=None if passed else "deterministic_check_failed")


async def judge(llm: LLM, settings: Settings, *, question: str, plan: QueryPlan, rf: ResolvedFilters,
                results: list[ToolResult], valid_zero: bool, financials_hidden: bool) -> tuple[JudgeVerdict, Usage]:
    data = {
        "question": question,
        "plan": {"intent": plan.intent, "metrics": plan.metrics, "tools": plan.tool_calls,
                 "group_by": plan.group_by, "quantity_unit": plan.quantity_unit},
        "resolved_filters": rf.model_dump(mode="json"),
        "valid_zero": valid_zero,
        "financials_hidden": financials_hidden,
        "results": [{"tool": r.tool, "row_count": r.row_count, "rows": r.rows[:50]} for r in results],
    }
    return await llm.parse(
        model=settings.openai_model_validator,
        system=load_prompt("validator"),
        user=f"<data>\n{json.dumps(data, ensure_ascii=False, default=str)}\n</data>",
        schema=JudgeVerdict,
    )
