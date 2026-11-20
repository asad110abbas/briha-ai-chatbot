"""Sheet size normalization (SPEC §6): '36 by 23' -> '23x36'."""

import re

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:x|×|\*|by|/|\s)\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)


def _fmt(v: float) -> str:
    return str(int(v)) if v.is_integer() else str(v)


def normalize_size(text: str | None) -> str | None:
    if text is None:
        return None
    m = _SIZE_RE.match(text.replace('"', "").replace("inch", "").replace("in", ""))
    if not m:
        return None
    a, b = sorted([float(m.group(1)), float(m.group(2))])
    return f"{_fmt(a)}x{_fmt(b)}"
