"""OFFLINE DEMO "LLM" - keyword rules instead of GPT-5 (LLM_MODE=offline_demo).

Only for trying the UI and pipeline before an OpenAI key is available. It understands a small set of
phrasings; real understanding quality comes from GPT-5. Never use this in production.
"""

import json
import re

from app.llm.client import Usage
from app.pipeline.orchestrator import guess_language
from app.pipeline.schemas import JudgeVerdict, QueryPlan

_DATES = [
    (r"\b(pichle|last)\s+(\d+)\s+(din|days)\b", "last_n_days"),
    (r"\b(aaj|today)\b", "today"),
    (r"\b(parson)\b", "day_before_yesterday"),
    (r"\b(kal|yesterday)\b", "yesterday"),
    (r"\b(is|this)\s+(hafte|week)\b", "this_week"),
    (r"\b(pichle|last)\s+(hafte|week)\b", "last_week"),
    (r"\b(is|this)\s+(mahine|month)\b", "this_month"),
    (r"\b(pichle|last)\s+(mahine|month)\b", "last_month"),
    (r"\b(is|this)\s+(saal|year)\b", "this_year"),
]
_PAPER = ["art paper", "art card", "bleach card", "bleach", "offset", "duplex", "kraft", "newsprint", "akhbari",
          "boxboard", "art"]
_GROUP = {"size": "size", "type": "paper_type", "quality": "paper_type", "gsm": "gsm", "din": "date",
          "daily": "date", "customer": "customer", "godown": "warehouse"}


class OfflineDemoLLM:
    async def parse(self, *, model, system, user, schema):
        if schema is JudgeVerdict:
            return JudgeVerdict(verdict="pass", issue=None, explanation="offline demo", fix_hint=None), Usage()
        payload = json.loads(user)
        return self._plan(payload["message"], payload.get("previous_context")), Usage()

    async def text(self, *, model, system, user):
        raise RuntimeError("offline demo uses the template answer")  # orchestrator falls back to template

    async def ping(self) -> bool:
        return True

    def _plan(self, msg: str, prev: dict | None) -> QueryPlan:
        m = msg.lower()
        lang = guess_language(msg)
        base = {"language": lang, "reply_language": None, "metrics": [], "tool_calls": [], "quantity_unit": None, "group_by": None,
                "clarification": None, "assumptions": [], "confidence": 0.5,
                "filters": {"date": {"expression": "none", "n": None, "from_date": None, "to_date": None},
                            "paper_type": None, "gsm": None, "size": None, "customer": None, "warehouse": None}}
        wants = re.search(r"\b(answer|reply|jawab|batao)\b.*\b(english|urdu)\b|\b(english|urdu)\s+mein\b", m)
        if wants:
            reply = "english" if "english" in wants.group(0) else "roman_urdu"
            return QueryPlan.model_validate({**base, "intent": "conversation", "reply_language": reply})
        if re.search(r"\b(update|add|delete|cancel|badal|hata)\b", m):
            return QueryPlan.model_validate({**base, "intent": "write_request"})
        if re.search(r"\b(agle|next|kal\s+kitna\s+bikega|forecast|weather|poem)\b", m):
            return QueryPlan.model_validate({**base, "intent": "out_of_scope"})

        tools, metrics = [], []
        if re.search(r"\b(kat|kata|kate|kati|kaati|cut|cutting)\b", m):
            tools.append("get_cutting_summary"); metrics.append("sheets_cut")
        if re.search(r"\b(bik|bika|bike|biki|bikin|sold|sale|sales|sell)\b", m):
            tools.append("get_sales_summary"); metrics.append("quantity_sold")
        if re.search(r"\b(stock|maal|available)\b", m):
            tools.append("get_stock_summary"); metrics += ["stock_sheets", "stock_reels"]

        f = base["filters"]
        for pattern, expr in _DATES:
            hit = re.search(pattern, m)
            if hit:
                f["date"]["expression"] = expr
                if expr == "last_n_days":
                    f["date"]["n"] = int(hit.group(2))
                break
        size = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|×|\*|by)\s*(\d+(?:\.\d+)?)", m)
        if size:
            f["size"] = f"{size.group(1)}x{size.group(2)}"
        f["paper_type"] = next((p for p in _PAPER if re.search(rf"\b{p}\b", m)), None)
        gsm = re.search(r"(\d{2,3})\s*(gsm|gram)", m)
        if gsm:
            f["gsm"] = int(gsm.group(1))
        group = re.search(r"\b(\w+)\s*(wise|wala)\b", m)
        group_by = _GROUP.get(group.group(1)) if group else None

        if not tools and prev:  # follow-up like "aur 23x36 ka?"
            tools, metrics = prev["tools"], prev["metrics"]
            rf = prev["resolved_filters"]
            if f["date"]["expression"] == "none":
                f["date"] = {"expression": "date_range", "n": None, "from_date": rf["date_from"], "to_date": rf["date_to"]}
            f["paper_type"] = f["paper_type"] or rf.get("paper_type_name")
            f["size"] = f["size"] or rf.get("size")
        if not tools:
            return QueryPlan.model_validate({**base, "intent": "help"})
        return QueryPlan.model_validate({**base, "intent": "data_query", "tool_calls": tools, "metrics": metrics,
                                         "group_by": group_by})
