from datetime import date

import pytest

from app.config import get_settings
from app.pipeline.agents.validator import deterministic_checks
from app.pipeline.grounding import allowed_numbers, ungrounded
from app.pipeline.resolve.dates import DateResolutionError, resolve_dates
from app.pipeline.resolve.entities import MasterItem, resolve_entity
from app.pipeline.resolve.sizes import normalize_size
from app.pipeline.schemas import ResolvedFilters, ToolResult
from tests.conftest import make_plan

TODAY = date(2026, 11, 3)
D = date.fromisoformat


@pytest.mark.parametrize("expr,n,frm,to,expected", [
    ("today", None, None, None, ("2026-11-03", "2026-11-03")),
    ("none", None, None, None, ("2026-11-03", "2026-11-03")),
    ("yesterday", None, None, None, ("2026-11-02", "2026-11-02")),
    ("day_before_yesterday", None, None, None, ("2026-11-01", "2026-11-01")),
    ("this_week", None, None, None, ("2026-11-02", "2026-11-03")),
    ("last_week", None, None, None, ("2026-10-26", "2026-11-01")),
    ("this_month", None, None, None, ("2026-11-01", "2026-11-03")),
    ("last_month", None, None, None, ("2026-10-01", "2026-10-31")),
    ("this_year", None, None, None, ("2026-01-01", "2026-11-03")),
    ("last_n_days", 7, None, None, ("2026-10-28", "2026-11-03")),
    ("specific_date", None, "12-15", None, ("2025-12-15", "2025-12-15")),
    ("specific_date", None, "2026-10-15", None, ("2026-10-15", "2026-10-15")),
    ("date_range", None, "10-01", "10-15", ("2026-10-01", "2026-10-15")),
])
def test_dates(expr, n, frm, to, expected):
    assert resolve_dates(expr, n, frm, to, TODAY) == (D(expected[0]), D(expected[1]))


@pytest.mark.parametrize("expr,frm,to,kind", [
    ("specific_date", "2026-11-10", None, "future"),
    ("date_range", "2025-01-01", "2026-11-03", "range_too_long"),
    ("specific_date", "nonsense", None, "invalid"),
    ("date_range", "2026-10-15", "2026-10-01", "invalid"),
])
def test_date_errors(expr, frm, to, kind):
    with pytest.raises(DateResolutionError) as exc:
        resolve_dates(expr, None, frm, to, TODAY)
    assert exc.value.kind == kind


@pytest.mark.parametrize("raw,expected", [
    ("23x36", "23x36"), ("23 x 36", "23x36"), ("23*36", "23x36"), ("23 by 36", "23x36"),
    ("36x23", "23x36"), ("36 X 23", "23x36"), ("23 36", "23x36"), ("23×36", "23x36"),
    ("25.5x36", "25.5x36"), ('23" x 36"', "23x36"), ("big size", None), ("23", None),
])
def test_sizes(raw, expected):
    assert normalize_size(raw) == expected


ITEMS = [MasterItem("ART_PAPER", "Art Paper"), MasterItem("ART_CARD", "Art Card"),
         MasterItem("BLEACH_CARD", "Bleach Card"), MasterItem("OFFSET", "Offset Paper")]
ALIASES = {"art paper": "ART_PAPER", "bleach": "BLEACH_CARD", "offset": "OFFSET"}


def test_entity_alias_and_exact():
    assert resolve_entity("Bleach", ITEMS, ALIASES).code == "BLEACH_CARD"
    assert resolve_entity("art card", ITEMS, ALIASES).code == "ART_CARD"
    assert resolve_entity("Art Paper", ITEMS, ALIASES).code == "ART_PAPER"


def test_entity_bare_art_is_ambiguous():  # SPEC AT-08 / review fix F2
    r = resolve_entity("art", ITEMS, ALIASES)
    assert r.status == "ambiguous"
    assert set(r.candidates[:2]) == {"Art Paper", "Art Card"}


def test_entity_fuzzy_typo_and_unknown():
    assert resolve_entity("bleech card", ITEMS, ALIASES).code == "BLEACH_CARD"
    assert resolve_entity("xyz zzz", ITEMS, ALIASES).status == "unknown"


def test_grounding():
    allowed = allowed_numbers({"cutting_total_sheets_cut": 18500, "x": 7}, "Aaj (3 Nov 2026)")
    assert ungrounded("Aaj (3 Nov 2026) **18,500 sheets**, 7 reels", allowed) == []
    assert ungrounded("Aaj **18,600 sheets**", allowed) == [18600.0]


def _rf(**kw):
    return ResolvedFilters(date_from=D("2026-11-03"), date_to=D("2026-11-03"), **kw)


def test_validator_detects_wrong_dates():
    plan = make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    r = ToolResult(tool="get_cutting_summary", ok=True, params={"date_from": "2026-11-03", "date_to": "2026-11-03"},
                   applied_filters={"date_from": "2026-10-04", "date_to": "2026-10-04"},
                   rows=[{"sheets_cut": 10}], row_count=1)
    v = deterministic_checks(plan, _rf(), [r], get_settings())
    assert not v.passed
    assert next(c for c in v.checks if c["id"] == "V2")["pass"] is False


def test_validator_valid_zero_and_missing_tool():
    plan = make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    empty = ToolResult(tool="get_cutting_summary", ok=True, params={"date_from": "2026-11-03"},
                       applied_filters={"date_from": "2026-11-03"}, rows=[], row_count=0)
    v = deterministic_checks(plan, _rf(), [empty], get_settings())
    assert v.passed and v.valid_zero  # review fix F3: V4 must not fail an empty result

    plan2 = make_plan(metrics=["sheets_cut", "quantity_sold"], tools=["get_cutting_summary"])
    v2 = deterministic_checks(plan2, _rf(), [empty], get_settings())
    assert not v2.passed and "get_sales_summary" in v2.fix_hint
