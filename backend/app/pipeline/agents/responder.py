"""Agent 4 - Response (SPEC §10): phrase validated facts in the user's language, then ground-check."""

import json
from typing import Any

from app.config import Settings
from app.llm.client import LLM, LLMError, Usage
from app.pipeline.agents.understanding import load_prompt
from app.pipeline.facts import TOOL_PREFIX
from app.pipeline.grounding import allowed_numbers, ungrounded
from app.pipeline.schemas import ToolResult

LABELS: dict[str, dict[str, str]] = {
    "cutting_total_sheets_cut": {"english": "sheets cut", "roman_urdu": "sheets kaati gayin"},
    "cutting_total_reels_used": {"english": "reels used", "roman_urdu": "reels use hue"},
    "cutting_total_weight_kg": {"english": "kg cut", "roman_urdu": "kg cutting"},
    "sales_total_quantity_sheets": {"english": "sheets sold", "roman_urdu": "sheets bikin"},
    "sales_total_invoice_count": {"english": "invoices", "roman_urdu": "invoices"},
    "sales_total_weight_kg": {"english": "kg sold", "roman_urdu": "kg sale"},
    "sales_total_amount_pkr": {"english": "PKR sales amount", "roman_urdu": "PKR sale amount"},
    "stock_total_quantity_sheets": {"english": "sheets in stock", "roman_urdu": "sheets stock mein"},
    "stock_total_reels": {"english": "reels in stock", "roman_urdu": "reels stock mein"},
    "stock_total_weight_kg": {"english": "kg total stock weight", "roman_urdu": "kg total stock weight"},
}
NOTHING = {
    "cutting": {"english": "no cutting was recorded", "roman_urdu": "koi cutting record nahi hui"},
    "sales": {"english": "no sales were recorded", "roman_urdu": "koi sale record nahi hui"},
    "stock": {"english": "no stock was found", "roman_urdu": "koi stock nahi mila"},
}


METRIC_FACT = {
    "sheets_cut": "cutting_total_sheets_cut", "reels_used": "cutting_total_reels_used",
    "weight_cut_kg": "cutting_total_weight_kg", "quantity_sold": "sales_total_quantity_sheets",
    "weight_sold_kg": "sales_total_weight_kg", "invoice_count": "sales_total_invoice_count",
    "amount_sold_pkr": "sales_total_amount_pkr", "stock_sheets": "stock_total_quantity_sheets",
    "stock_reels": "stock_total_reels", "stock_weight_kg": "stock_total_weight_kg",
}
PRIMARY = {"cutting": "cutting_total_sheets_cut", "sales": "sales_total_quantity_sheets",
           "stock": "stock_total_quantity_sheets"}


def template_answer(language: str, label: str, facts: dict[str, Any], results: list[ToolResult],
                    assumptions: list[str], metrics: list[str] | None = None) -> str:
    """Deterministic fallback: always grounded. Shows the requested metrics in a fixed order."""
    lang = language if language in LABELS["cutting_total_sheets_cut"] else "english"
    wanted = {METRIC_FACT[m] for m in (metrics or []) if m in METRIC_FACT}
    parts = []
    for r in results:
        prefix = TOOL_PREFIX[r.tool]
        keys = [k for k in LABELS if k.startswith(prefix) and facts.get(k) is not None]
        chosen = [k for k in keys if k in wanted] or [k for k in keys if k == PRIMARY[prefix]] or keys[:1]
        if not chosen:
            parts.append(NOTHING[prefix][lang])
            continue
        parts.append(", ".join(f"**{facts[k]:,}** {LABELS[k][lang]}" for k in chosen))
    joiner = " aur " if lang == "roman_urdu" else "; "
    text = f"{label}: {joiner.join(parts)}."
    if assumptions:
        text += "\n\n" + " ".join(assumptions)
    return text


async def respond(llm: LLM, settings: Settings, *, question: str, language: str, label: str,
                  chips: dict[str, str], facts: dict[str, Any], results: list[ToolResult], assumptions: list[str],
                  valid_zero: bool, financials_hidden: bool, table_shown: bool,
                  metrics: list[str] | None = None) -> tuple[str, bool, Usage]:
    """Returns (text, used_template, usage)."""
    rows = {TOOL_PREFIX[r.tool]: r.rows[:20] for r in results}
    allowed = allowed_numbers(facts, rows, chips, label, question)
    data = {
        "question": question, "date_label": label, "filters": chips, "facts": facts, "rows": rows,
        "assumptions": assumptions, "valid_zero": valid_zero, "financials_hidden": financials_hidden,
        "table_shown": table_shown,
    }
    system = load_prompt("responder").format(
        language_name="Roman Urdu" if language == "roman_urdu" else "English")
    usage = Usage()
    note = ""
    for _ in range(2):  # generate, then regenerate once if ungrounded
        try:
            text, u = await llm.text(
                model=settings.openai_model_responder, system=system,
                user=f"{note}<data>\n{json.dumps(data, ensure_ascii=False, default=str)}\n</data>",
            )
        except (LLMError, RuntimeError):
            break
        usage.input_tokens += u.input_tokens
        usage.output_tokens += u.output_tokens
        bad = ungrounded(text, allowed)
        if text and not bad:
            return text, False, usage
        note = (f"Your previous answer contained numbers not in the data: {bad}. Use only numbers from facts "
                "or rows, exactly as given.\n")
    return template_answer(language, label, facts, results, assumptions, metrics), True, usage
