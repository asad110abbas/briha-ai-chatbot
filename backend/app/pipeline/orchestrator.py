"""Orchestrator (SPEC §3): Understanding -> Resolving -> Retrieving -> Validating -> Responding -> Grounding.

`run()` is an async generator of (event, data) tuples:
  ("status", {...}) / ("clarification", {...}) while working, and finally ("outcome", RunOutcome).
The API layer persists the outcome, then streams the answer text and `done` (SPEC O3, O5).
"""

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.datasources.base import DataSource, DataSourceError
from app.llm.client import LLM, LLMError, Usage
from app.pipeline.agents.conversation import converse
from app.pipeline.agents.responder import respond
from app.pipeline.agents.retrieval import retrieve
from app.pipeline.agents.understanding import understand
from app.pipeline.agents.validator import Validation, deterministic_checks, judge
from app.pipeline.catalog import Glossary, MasterCache
from app.pipeline.facts import build_facts, build_table, date_label, filter_chips, fmt_date
from app.pipeline.resolve.dates import DateResolutionError, resolve_dates
from app.pipeline.resolve.entities import resolve_entity
from app.pipeline.resolve.sizes import normalize_size
from app.pipeline.schemas import QueryPlan, ResolvedFilters, ToolResult
from app.pipeline.texts import KIND_NAMES, t

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
_URDU_HINT = re.compile(
    r"\b(kitna|kitne|kitni|hai|hain|aaj|kal|ka|ki|ke|mein|kya|bika|bike|kata|kate|karo|kar|batao|aur|tha)\b", re.IGNORECASE
)


def guess_language(text: str) -> str:
    return "roman_urdu" if len(_URDU_HINT.findall(text)) >= 1 or re.search(r"[؀-ۿ]", text) else "english"


@dataclass
class RunInput:
    message: str
    history: list[dict[str, str]]
    previous_context: dict[str, Any] | None
    pending_clarification: dict[str, Any] | None
    can_view_financials: bool
    glossary: Glossary
    preferred_language: str | None = None  # set once the user asks "answer in English / Roman Urdu"


@dataclass
class RunOutcome:
    content: str
    status: str
    language: str
    ui_payload: dict[str, Any]
    record: dict[str, Any]
    error_code: str | None = None


@dataclass
class _Clarify:
    question: str
    options: list[str]


@dataclass
class _Refuse:
    text: str


@dataclass
class _Record:
    started: float = field(default_factory=time.perf_counter)
    plan: dict | None = None
    resolved_filters: dict | None = None
    tool_calls: list | None = None
    result_preview: list | None = None
    attempts_log: list = field(default_factory=list)
    attempts: int = 1
    stage_ms: dict[str, int] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    preferred_language: str | None = None

    def usage(self, u: Usage) -> None:
        self.tokens_in += u.input_tokens
        self.tokens_out += u.output_tokens

    def stage(self, name: str, since: float) -> None:
        self.stage_ms[name] = self.stage_ms.get(name, 0) + int((time.perf_counter() - since) * 1000)


class Orchestrator:
    def __init__(self, llm: LLM, ds: DataSource, settings: Settings, master: MasterCache):
        self.llm, self.ds, self.settings, self.master = llm, ds, settings, master

    async def run(self, inp: RunInput) -> AsyncIterator[tuple[str, Any]]:
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def emit(event: str, data: dict[str, Any]) -> None:
            await queue.put((event, data))

        rec = _Record()
        task = asyncio.create_task(self._guarded(inp, emit, rec))
        try:
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield getter.result()
                    continue
                getter.cancel()
                while not queue.empty():
                    yield queue.get_nowait()
                yield ("outcome", task.result())
                return
        finally:
            if not task.done():
                task.cancel()

    async def _guarded(self, inp: RunInput, emit: Emit, rec: _Record) -> RunOutcome:
        rec.preferred_language = inp.preferred_language
        language = inp.preferred_language or guess_language(inp.message)
        try:
            return await asyncio.wait_for(self._execute(inp, emit, rec), timeout=self.settings.run_timeout_seconds)
        except TimeoutError:
            return self._finish(rec, t("TIMEOUT", language), "error", language, {}, error_code="TIMEOUT")
        except Exception:  # noqa: BLE001 - never leak a stack trace to the user
            import structlog

            structlog.get_logger().exception("run_failed")
            return self._finish(rec, t("INTERNAL", language), "error", language, {}, error_code="INTERNAL")

    # ------------------------------------------------------------------------------------------
    async def _execute(self, inp: RunInput, emit: Emit, rec: _Record) -> RunOutcome:
        s = self.settings
        language = inp.preferred_language or guess_language(inp.message)
        fix_hint: str | None = None
        plan: QueryPlan | None = None
        rf: ResolvedFilters | None = None
        results: list[ToolResult] = []
        validation: Validation | None = None
        assumptions: list[str] = []

        try:
            master = await self.master.get()
        except DataSourceError as exc:
            return self._finish(rec, t(exc.code, language), "error", language, {}, error_code=exc.code)

        for attempt in (1, 2):
            rec.attempts = attempt
            await emit("status", {"stage": "understanding", "attempt": attempt})
            t0 = time.perf_counter()
            try:
                plan, u = await understand(
                    self.llm, s, message=inp.message, history=inp.history, previous_context=inp.previous_context,
                    pending_clarification=inp.pending_clarification, fix_hint=fix_hint,
                    glossary=inp.glossary.kind("paper_type"), paper_types=[p.name for p in master.paper_types],
                )
            except LLMError:
                return self._finish(rec, t("LLM_UNAVAILABLE", language), "error", language, {},
                                    error_code="LLM_UNAVAILABLE")
            rec.usage(u)
            rec.stage("understanding", t0)
            rec.plan = plan.model_dump(mode="json")
            # A language the user asked for wins (now, or earlier in this chat). Otherwise trust the model,
            # but if the message clearly has Roman Urdu words, answer in Roman Urdu.
            # The model sometimes repeats an old request it sees in history; only a change counts as a new one.
            language_changed = bool(plan.reply_language) and plan.reply_language != inp.preferred_language
            if plan.reply_language:
                rec.preferred_language = plan.reply_language
            language = rec.preferred_language or (
                "roman_urdu" if guess_language(inp.message) == "roman_urdu" else plan.language)
            plan.language = language  # type: ignore[assignment]

            if plan.intent == "help":
                return self._finish(rec, t("help", language), "answered", language, {})
            if plan.intent == "conversation":
                if language_changed:
                    return self._finish(rec, t("language_set", language), "answered", language, {})
                await emit("status", {"stage": "responding", "attempt": attempt})
                t0 = time.perf_counter()
                text, used_fallback, u = await converse(
                    self.llm, s, message=inp.message, language=language, history=inp.history,
                    previous_context=inp.previous_context,
                )
                rec.usage(u)
                rec.stage("responding", t0)
                return self._finish(rec, text, "answered", language, {"template": used_fallback})
            if plan.intent in ("write_request", "out_of_scope"):
                return self._finish(rec, t(plan.intent, language), "refused", language, {})
            if plan.intent == "clarification_needed" or not plan.tool_calls:
                c = plan.clarification
                question = c.question if c else t("which_metric", language)
                options = (c.options if c else None) or (
                    ["Kaata hua", "Bika hua"] if language == "roman_urdu" else ["Cut", "Sold"])
                return await self._clarify(emit, rec, language, question, options[:4], plan)

            resolved = self._resolve(plan, master, inp.glossary, language)
            if isinstance(resolved, _Refuse):
                return self._finish(rec, resolved.text, "refused", language, {})
            if isinstance(resolved, _Clarify):
                return await self._clarify(emit, rec, language, resolved.question, resolved.options, plan)
            rf, assumptions = resolved
            rec.resolved_filters = rf.model_dump(mode="json")

            await emit("status", {"stage": "retrieving", "attempt": attempt})
            t0 = time.perf_counter()
            try:
                results = await retrieve(self.ds, s, plan.tool_calls, rf, inp.can_view_financials)
            except DataSourceError as exc:
                rec.stage("retrieving", t0)
                return self._finish(rec, t(exc.code, language), "error", language, {}, error_code=exc.code)
            rec.stage("retrieving", t0)
            rec.tool_calls = [
                {"tool": r.tool, "params": r.params, "source_ref": r.source_ref, "ok": r.ok, "row_count": r.row_count,
                 "duration_ms": r.duration_ms, "error": r.error, "truncated": r.truncated} for r in results
            ]
            rec.result_preview = [{"tool": r.tool, "rows": r.rows[:50]} for r in results]

            await emit("status", {"stage": "validating", "attempt": attempt})
            t0 = time.perf_counter()
            validation = deterministic_checks(plan, rf, results, s)
            if validation.passed and s.validator_llm_enabled:
                try:
                    verdict, u = await judge(
                        self.llm, s, question=inp.message, plan=plan, rf=rf, results=results,
                        valid_zero=validation.valid_zero, financials_hidden=not inp.can_view_financials,
                    )
                    rec.usage(u)
                    validation.llm_verdict = verdict.verdict
                    if verdict.verdict == "fail":
                        validation.passed = False
                        validation.issue = verdict.issue
                        validation.fix_hint = verdict.fix_hint or verdict.explanation
                except LLMError:
                    validation.llm_verdict = "unavailable"  # deterministic checks stay authoritative
            rec.stage("validating", t0)
            rec.attempts_log.append({"attempt": attempt, "plan": rec.plan, **validation.as_json()})
            if validation.passed:
                break
            fix_hint = validation.fix_hint or "The data did not match the question. Re-check tools and filters."

        assert plan is not None and validation is not None
        if not validation.passed or rf is None:
            # Which checks failed stays in the admin log; the user gets a plain-language reason.
            code_check_failed = any(not c["pass"] for c in validation.checks)
            text = t("data_check_failed" if code_check_failed else "no_matching_data", language)
            return self._finish(rec, text, "no_data", language,
                                {"verified": False}, validation=validation)

        # ---- respond ----------------------------------------------------------------------
        await emit("status", {"stage": "responding", "attempt": rec.attempts})
        t0 = time.perf_counter()
        today = s.today()
        label = date_label(rf, today, language)
        if plan.tool_calls == ["get_stock_summary"]:
            label = f"Stock as of {fmt_date(rf.date_to)}" if language == "english" else f"Stock ({fmt_date(rf.date_to)})"
        chips = filter_chips(rf, plan.tool_calls)
        facts = build_facts(results, rf, s.ream_size_sheets)
        table = build_table(results, rf)
        text, used_template, u = await respond(
            self.llm, s, question=inp.message, language=language, label=label, chips=chips, facts=facts,
            results=results, assumptions=assumptions, valid_zero=validation.valid_zero,
            financials_hidden=not inp.can_view_financials, table_shown=table is not None,
            metrics=list(plan.metrics),
        )
        rec.usage(u)
        rec.stage("responding", t0)
        ui = {
            "filters": chips, "assumptions": assumptions, "table": table, "verified": True,
            "template": used_template,
            "context": {"metrics": plan.metrics, "tools": plan.tool_calls, "group_by": plan.group_by,
                        "quantity_unit": plan.quantity_unit, "resolved_filters": rf.model_dump(mode="json")},
        }
        return self._finish(rec, text, "answered", language, ui, validation=validation)

    # ------------------------------------------------------------------------------------------
    def _resolve(self, plan: QueryPlan, master, glossary: Glossary, language: str
                 ) -> tuple[ResolvedFilters, list[str]] | _Clarify | _Refuse:
        f = plan.filters
        today = self.settings.today()
        try:
            d_from, d_to = resolve_dates(f.date.expression, f.date.n, f.date.from_date, f.date.to_date, today)
        except DateResolutionError as exc:
            if exc.kind == "future":
                return _Refuse(t("future", language))
            if exc.kind == "range_too_long":
                return _Clarify(t("range_too_long", language), [])
            opts = ["Aaj", "Kal", "Is hafte"] if language == "roman_urdu" else ["Today", "Yesterday", "This week"]
            return _Clarify(t("bad_date", language), opts)

        assumptions: list[str] = []
        if f.date.expression == "none" and plan.tool_calls != ["get_stock_summary"]:
            assumptions.append(t("assumed_today", language))

        rf = ResolvedFilters(date_from=d_from, date_to=d_to, group_by=plan.group_by, quantity_unit=plan.quantity_unit)

        for kind, raw, items, code_attr, name_attr in (
            ("paper_type", f.paper_type, master.paper_types, "paper_type_code", "paper_type_name"),
            ("customer", f.customer, master.customers, "customer_code", "customer_name"),
            ("warehouse", f.warehouse, master.warehouses, "warehouse_code", "warehouse_name"),
        ):
            if not raw:
                continue
            res = resolve_entity(raw, items, glossary.kind(kind))
            kind_name = KIND_NAMES[kind][language]
            if res.status == "ambiguous":
                return _Clarify(t("which_entity", language, kind=kind_name), res.candidates[:3])
            if res.status == "unknown":
                return _Clarify(t("unknown_entity", language, kind=kind_name, value=raw), res.candidates[:3])
            setattr(rf, code_attr, res.code)
            setattr(rf, name_attr, res.name)

        if f.size:
            size = normalize_size(f.size)
            if size is None:
                return _Clarify(t("bad_size", language, value=f.size), [])
            rf.size = size
        if f.gsm is not None:
            if not 30 <= f.gsm <= 600:
                return _Clarify(t("bad_gsm", language), [])
            rf.gsm = f.gsm
        return rf, assumptions

    async def _clarify(self, emit: Emit, rec: _Record, language: str, question: str, options: list[str],
                       plan: QueryPlan) -> RunOutcome:
        await emit("clarification", {"question": question, "options": options})
        ui = {"clarification_options": options, "pending_plan": plan.model_dump(mode="json")}
        return self._finish(rec, question, "clarification", language, ui)

    def _finish(self, rec: _Record, content: str, status: str, language: str, ui: dict[str, Any],
                error_code: str | None = None, validation: Validation | None = None) -> RunOutcome:
        s = self.settings
        if rec.preferred_language:  # saved with the message so the next turn keeps the user's choice
            ui = {**ui, "preferred_language": rec.preferred_language}
        cost = (rec.tokens_in * s.openai_price_input_per_m + rec.tokens_out * s.openai_price_output_per_m) / 1e6
        record = {
            "plan": rec.plan,
            "resolved_filters": rec.resolved_filters,
            "tool_calls": rec.tool_calls,
            "result_preview": rec.result_preview,
            "validation": {"final": validation.as_json() if validation else None, "attempts": rec.attempts_log},
            "attempts": rec.attempts,
            "final_status": status,
            "error_code": error_code,
            "stage_latency_ms": rec.stage_ms,
            "total_latency_ms": int((time.perf_counter() - rec.started) * 1000),
            "tokens_input": rec.tokens_in,
            "tokens_output": rec.tokens_out,
            "estimated_cost_usd": Decimal(str(round(cost, 5))),
        }
        return RunOutcome(content=content, status=status, language=language, ui_payload=ui, record=record,
                          error_code=error_code)
