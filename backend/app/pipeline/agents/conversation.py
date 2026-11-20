"""Conversation replies: messages about the chat itself ("is this accurate?", "what did I ask before?").

No tools run here, so the reply may only repeat numbers already present in the chat; otherwise a fixed text is used.
"""

import json
from typing import Any

from app.config import Settings
from app.llm.client import LLM, LLMError, Usage
from app.pipeline.agents.understanding import load_prompt
from app.pipeline.grounding import allowed_numbers, ungrounded
from app.pipeline.texts import t

DATA_SOURCES = {
    "mock": "sample test data (not real company figures)",
    "rest": "the live company data system",
}


async def converse(llm: LLM, settings: Settings, *, message: str, language: str, history: list[dict[str, str]],
                   previous_context: dict[str, Any] | None) -> tuple[str, bool, Usage]:
    """Returns (text, used_fallback, usage)."""
    data = {
        "history": history, "previous_context": previous_context,
        "data_source": DATA_SOURCES.get(settings.datasource_mode, settings.datasource_mode), "message": message,
    }
    allowed = allowed_numbers(history, previous_context, message)
    system = load_prompt("conversation").format(
        language_name="Roman Urdu" if language == "roman_urdu" else "English")
    usage = Usage()
    note = ""
    for _ in range(2):  # generate, then regenerate once if it invented a number
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
        note = f"Your previous reply contained numbers that are not in the chat: {bad}. Do not state them.\n"
    return t("conversation_fallback", language), True, usage
