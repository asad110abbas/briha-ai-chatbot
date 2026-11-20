"""REST adapter with several company APIs, each with its own field names (data_apis.yaml)."""

import json
from datetime import date

import httpx
import pytest

from app.config import get_settings
from app.datasources.base import DataSourceError
from app.datasources.rest import ConfigError, RestDataSource

CONFIG = """
date_format: "%d/%m/%Y"
apis:
  - tool: get_cutting_summary
    url: "http://erp.local:8085/api/cutting"
    api_key_env: TEST_CUT_KEY
    auth_header: "X-API-Key"
    params: {date_from: fromDate, date_to: toDate}
    rows_path: "data.items"
    fields: {date: CutDate, paper_type: Quality, gsm: GSM, size: SheetSize, sheets_cut: Sheets,
             weight_kg: Kg, reel_id: ReelNo}
  - tool: get_sales_summary
    url: "http://sales.local:9000/sales"
    params: {}
    rows_path: ""
    fields: {date: InvDate, invoice_no: InvNo, paper_type: Item, size: Size, quantity_sheets: Qty, amount_pkr: Amt}
  - tool: get_stock_summary
    url: "http://inv.local:7000/inventory"
    method: POST
    params: {as_of: asOn}
    rows_path: "items"
    fields: {paper_type: ItemName, size: Size, warehouse: Godown, form: Form, quantity_sheets: Sheets, reels: Reels}
master_data:
  paper_types:
    static:
      - {code: ART_PAPER, name: Art Paper}
      - {code: OFFSET, name: Offset Paper}
"""

CUTTING = {"data": {"items": [
    {"CutDate": "03/11/2026", "Quality": "Art Paper", "GSM": "128", "SheetSize": "36 x 23", "Sheets": "1,000",
     "Kg": 120.5, "ReelNo": "R1"},
    {"CutDate": "03/11/2026", "Quality": "ART_PAPER", "GSM": 128, "SheetSize": "23x36", "Sheets": 500, "Kg": 60,
     "ReelNo": "R1"},
    {"CutDate": "03/11/2026", "Quality": "Offset Paper", "GSM": 80, "SheetSize": "20x30", "Sheets": 700, "Kg": 50,
     "ReelNo": "R2"},
]}}
# this API ignores dates, so BRIHA must filter them itself
SALES = [
    {"InvDate": "2026-11-02T10:00:00", "InvNo": "A1", "Item": "Art Paper", "Size": "23*36", "Qty": 400, "Amt": 9000},
    {"InvDate": "2026-11-02", "InvNo": "A1", "Item": "Offset Paper", "Size": "20x30", "Qty": 100, "Amt": 2000},
    {"InvDate": "2026-11-02", "InvNo": "A2", "Item": "Art Paper", "Size": "23x36", "Qty": 600, "Amt": 12000},
    {"InvDate": "2026-10-15", "InvNo": "B9", "Item": "Art Paper", "Size": "23x36", "Qty": 9999, "Amt": 1},
]
STOCK = {"items": [
    {"ItemName": "Art Paper", "Size": "23x36", "Godown": "MAIN", "Form": "Sheet", "Sheets": 5000, "Reels": None},
    {"ItemName": "Art Paper", "Size": None, "Godown": "MAIN", "Form": "Reel", "Sheets": None, "Reels": 4},
]}


@pytest.fixture
def seen():
    return []


@pytest.fixture
def ds(tmp_path, monkeypatch, seen):
    monkeypatch.setenv("TEST_CUT_KEY", "secret-123")
    cfg = tmp_path / "data_apis.yaml"
    cfg.write_text(CONFIG)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "erp.local":
            return httpx.Response(200, json=CUTTING)
        if request.url.host == "sales.local":
            return httpx.Response(200, json=SALES)
        if request.url.host == "inv.local":
            return httpx.Response(200, json=STOCK)
        return httpx.Response(404)

    return RestDataSource(get_settings(), cfg, transport=httpx.MockTransport(handler))


async def test_cutting_maps_fields_and_sends_params(ds, seen):
    r = await ds.run_tool("get_cutting_summary", {"date_from": date(2026, 11, 3), "date_to": date(2026, 11, 3),
                                                  "paper_type_code": None, "gsm": None, "size": None, "group_by": None})
    assert r.rows == [{"sheets_cut": 2200, "weight_kg": 230.5, "reels_used": 2}]
    req = seen[0]
    assert req.url.params["fromDate"] == "03/11/2026" and req.headers["X-API-Key"] == "secret-123"


async def test_cutting_filter_by_paper_and_size_and_group(ds):
    r = await ds.run_tool("get_cutting_summary", {"date_from": date(2026, 11, 3), "date_to": date(2026, 11, 3),
                                                  "paper_type_code": "ART_PAPER", "gsm": 128, "size": "23x36",
                                                  "group_by": "size"})
    assert r.rows == [{"size": "23x36", "sheets_cut": 1500, "weight_kg": 180.5, "reels_used": 1}]


async def test_sales_local_date_filter_and_distinct_invoices(ds):
    r = await ds.run_tool("get_sales_summary", {"date_from": date(2026, 11, 2), "date_to": date(2026, 11, 2),
                                                "paper_type_code": "ART_PAPER", "gsm": None, "size": "23x36",
                                                "customer_code": None, "group_by": None})
    assert r.rows == [{"quantity_sheets": 1000, "amount_pkr": 21000, "invoice_count": 2}]


async def test_stock_post_and_group_by_form(ds, seen):
    r = await ds.run_tool("get_stock_summary", {"as_of": date(2026, 11, 3), "paper_type_code": "ART_PAPER",
                                                "gsm": None, "size": None, "warehouse_code": None, "form": None,
                                                "group_by": "form"})
    assert r.rows == [{"form": "reel", "reels": 4}, {"form": "sheet", "quantity_sheets": 5000}]
    assert seen[-1].method == "POST" and json.loads(seen[-1].content) == {"asOn": "03/11/2026"}


async def test_api_down_and_missing_config(tmp_path):
    cfg = tmp_path / "data_apis.yaml"
    cfg.write_text(CONFIG)
    broken = RestDataSource(get_settings(), cfg,
                            transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(DataSourceError) as exc:
        await broken.run_tool("get_sales_summary", {"date_from": date(2026, 11, 2), "date_to": date(2026, 11, 2)})
    assert exc.value.code == "DATA_SOURCE_UNAVAILABLE"
    with pytest.raises(ConfigError):
        RestDataSource(get_settings(), tmp_path / "missing.yaml")
