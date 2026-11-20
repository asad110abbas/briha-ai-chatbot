"""Agent 1 - Query Understanding (SPEC §4)."""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from app.config import Settings
from app.llm.client import LLM, Usage
from app.pipeline.schemas import TOOLS, QueryPlan

PROMPTS = Path(__file__).resolve().parents[2] / "llm" / "prompts"


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def build_system(today: date, glossary: dict[str, str], paper_types: list[str]) -> str:
    return load_prompt("understanding").format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        glossary=", ".join(f"{a} -> {c}" for a, c in sorted(glossary.items())) or "(none)",
        paper_types=", ".join(paper_types) or "(unknown)",
    )


async def understand(
    llm: LLM,
    settings: Settings,
    *,
    message: str,
    history: list[dict[str, str]],
    previous_context: dict[str, Any] | None,
    pending_clarification: dict[str, Any] | None,
    fix_hint: str | None,
    glossary: dict[str, str],
    paper_types: list[str],
) -> tuple[QueryPlan, Usage]:
    payload = {
        "history": history,
        "previous_context": previous_context,
        "pending_clarification": pending_clarification,
        "fix_hint": fix_hint,
        "message": message,
    }
    plan, usage = await llm.parse(
        model=settings.openai_model_understanding,
        system=build_system(settings.today(), glossary, paper_types),
        user=json.dumps(payload, ensure_ascii=False, default=str),
        schema=QueryPlan,
    )
    # Defensive normalisation (Pydantic enforces types; these are rule limits from SPEC U3).
    plan.tool_calls = [t for i, t in enumerate(plan.tool_calls) if t in TOOLS and t not in plan.tool_calls[:i]][:3]
    return plan, usage
