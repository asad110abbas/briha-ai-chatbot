"""Paper type / customer / warehouse resolution (SPEC §6): glossary -> exact -> fuzzy -> clarify."""

from dataclasses import dataclass, field
from typing import Literal

from rapidfuzz import fuzz, process, utils


@dataclass(frozen=True)
class MasterItem:
    code: str
    name: str


@dataclass
class Resolution:
    status: Literal["ok", "ambiguous", "unknown"]
    code: str | None = None
    name: str | None = None
    candidates: list[str] = field(default_factory=list)  # display names


def resolve_entity(raw: str, items: list[MasterItem], aliases: dict[str, str]) -> Resolution:
    by_code = {i.code: i for i in items}
    s = raw.strip().lower()

    code = aliases.get(s)
    if code and code in by_code:
        return Resolution("ok", code, by_code[code].name)
    for item in items:
        if s in (item.code.lower(), item.name.lower()):
            return Resolution("ok", item.code, item.name)

    names = [i.name for i in items]
    matches = process.extract(s, names, scorer=fuzz.WRatio, processor=utils.default_process, limit=3)
    if not matches:
        return Resolution("unknown")
    top_name, top_score, _ = matches[0]
    close = [m for m in matches[1:] if m[1] >= 80 and top_score - m[1] <= 5]
    top_item = next(i for i in items if i.name == top_name)
    if top_score >= 90 and not close:
        return Resolution("ok", top_item.code, top_item.name)
    if top_score >= 80:
        return Resolution("ambiguous", candidates=[top_name] + [m[0] for m in close])
    return Resolution("unknown", candidates=[m[0] for m in matches])
