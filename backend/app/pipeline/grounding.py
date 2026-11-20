"""Number grounding check (SPEC §10): every number in the answer must come from the data."""

import re
from datetime import date
from typing import Any

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(token: str) -> float | None:
    try:
        return round(float(token.replace(",", "")), 2)
    except ValueError:
        return None


def numbers_in(text: str) -> list[float]:
    return [n for n in (_norm(t) for t in _NUM.findall(text)) if n is not None]


def _collect(value: Any, out: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.add(round(float(value), 2))
    elif isinstance(value, date):
        out.update({float(value.day), float(value.month), float(value.year)})
    elif isinstance(value, str):
        out.update(numbers_in(value))
    elif isinstance(value, dict):
        for v in value.values():
            _collect(v, out)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            _collect(v, out)


def allowed_numbers(*sources: Any) -> set[float]:
    out: set[float] = set()
    for s in sources:
        _collect(s, out)
    return out


def ungrounded(text: str, allowed: set[float]) -> list[float]:
    return [n for n in numbers_in(text) if n not in allowed]
