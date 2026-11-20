"""REST adapter for the company's data APIs (several APIs, configured in /data_apis.yaml).

Each catalogued tool (cutting / sales / stock) is mapped to ONE company API in the YAML file:
URL, auth, which query parameters it accepts, where the rows are in the JSON, and what the fields are
called. BRIHA then:
  1. calls only that URL (GPT never chooses URLs, only the tool),
  2. maps the API's field names to BRIHA's names,
  3. filters anything the API couldn't filter itself (date, paper type, size, GSM, ...),
  4. sums / groups the rows itself, so APIs that return raw lines work as well as summary APIs.
"""

import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.config import ROOT_DIR, Settings
from app.datasources.base import DataSourceError, MasterData, iso
from app.pipeline.resolve.entities import MasterItem
from app.pipeline.resolve.sizes import normalize_size
from app.pipeline.schemas import ToolResult

TOOLS = ("get_cutting_summary", "get_sales_summary", "get_stock_summary")
# metric fields BRIHA sums per tool, and the "count distinct" fields
SUM_FIELDS = {
    "get_cutting_summary": ("sheets_cut", "weight_kg", "reels_used"),
    "get_sales_summary": ("quantity_sheets", "weight_kg", "amount_pkr", "invoice_count"),
    "get_stock_summary": ("quantity_sheets", "reels", "weight_kg"),
}
DISTINCT = {"reels_used": "reel_id", "invoice_count": "invoice_no"}
GROUP_FIELDS = {"date": "date", "paper_type": "paper_type", "gsm": "gsm", "size": "size",
                "customer": "customer", "warehouse": "warehouse", "form": "form"}


class ConfigError(RuntimeError):
    pass


@dataclass
class ApiSpec:
    tool: str
    url: str
    method: str = "GET"
    api_key_env: str | None = None
    auth_header: str = "X-API-Key"
    params: dict[str, str] = field(default_factory=dict)
    rows_path: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    description: str = ""


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"DATASOURCE_MODE=rest but {path.name} not found. Copy data_apis.example.yaml to "
                          f"data_apis.yaml and fill it in.")
    cfg = yaml.safe_load(path.read_text()) or {}
    apis = cfg.get("apis") or []
    specs = {}
    for a in apis:
        spec = ApiSpec(**{k: v for k, v in a.items() if k in ApiSpec.__dataclass_fields__})
        if spec.tool not in TOOLS:
            raise ConfigError(f"Unknown tool {spec.tool!r} in {path.name}; use one of {TOOLS}")
        specs[spec.tool] = spec
    cfg["_specs"] = specs
    return cfg


def _dig(body: Any, path: str) -> Any:
    for part in [p for p in (path or "").split(".") if p]:
        if not isinstance(body, dict) or part not in body:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"rows_path '{path}' not found in API response")
        body = body[part]
    return body


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


class RestDataSource:
    mode = "rest"

    def __init__(self, settings: Settings, config_path: Path | None = None, transport=None):
        self.settings = settings
        self.cfg = load_config(config_path or ROOT_DIR / "data_apis.yaml")
        self.specs: dict[str, ApiSpec] = self.cfg["_specs"]
        self.date_format = self.cfg.get("date_format", "%Y-%m-%d")
        self._client = httpx.AsyncClient(timeout=settings.tool_timeout_seconds,
                                         verify=settings.data_api_verify_tls, transport=transport)
        self._codes: dict[str, str] = {}  # lowercased code/name -> code (filled from master data)

    # ---- HTTP -----------------------------------------------------------------------------
    def _headers(self, key_env: str | None, header: str) -> dict[str, str]:
        h = {"Accept": "application/json"}
        key = os.environ.get(key_env or "") or (self._env_file_value(key_env) if key_env else None)
        if key:
            h[header] = key
        return h

    @staticmethod
    def _env_file_value(name: str) -> str | None:
        env = ROOT_DIR / ".env"
        if not env.exists():
            return None
        for line in env.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
        return None

    async def _call(self, url: str, method: str, headers: dict, params: dict) -> Any:
        try:
            if method.upper() == "POST":
                r = await self._client.post(url, json=params, headers=headers)
            else:
                r = await self._client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise DataSourceError("DATA_SOURCE_TIMEOUT", f"{url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"{url}: {exc}") from exc
        if r.status_code >= 400:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"HTTP {r.status_code} from {url}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError as exc:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"{url} did not return JSON") from exc

    # ---- normalisation --------------------------------------------------------------------
    def _parse_date(self, v: Any) -> date | None:
        if v in (None, ""):
            return None
        text = str(v).strip()
        try:  # ISO: 2026-11-03, 2026-11-03T10:15:00, 2026-11-03T10:15:00Z
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
        for fmt in (self.date_format, "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _code(self, v: Any) -> str | None:
        if v in (None, ""):
            return None
        s = str(v).strip()
        return self._codes.get(s.lower(), s)

    def _normalize(self, raw: dict[str, Any], spec: ApiSpec) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for ours, theirs in spec.fields.items():
            row[ours] = raw.get(theirs)
        if "date" in row:
            row["date"] = self._parse_date(row["date"])
        if row.get("size") not in (None, ""):
            row["size"] = normalize_size(str(row["size"])) or str(row["size"])
        if row.get("gsm") not in (None, ""):
            g = _num(row["gsm"])
            row["gsm"] = int(g) if g is not None else None
        if "paper_type" in row:
            row["paper_type"] = self._code(row["paper_type"])
        if row.get("form"):
            row["form"] = str(row["form"]).strip().lower()
        for k in ("sheets_cut", "quantity_sheets", "weight_kg", "amount_pkr", "reels"):
            if k in row:
                row[k] = _num(row[k])
        return row

    @staticmethod
    def _matches(row: dict[str, Any], p: dict[str, Any]) -> bool:
        if p.get("date_from") and row.get("date") and not (p["date_from"] <= row["date"] <= p["date_to"]):
            return False
        for ours, key in (("paper_type", "paper_type_code"), ("gsm", "gsm"), ("size", "size"),
                          ("customer", "customer_code"), ("warehouse", "warehouse_code"), ("form", "form")):
            want = p.get(key)
            if want is not None and ours in row and str(row[ours]).lower() != str(want).lower():
                return False
        return True

    def _aggregate(self, tool: str, rows: list[dict[str, Any]], group_by: str | None) -> list[dict[str, Any]]:
        groups: dict[Any, dict[str, Any]] = {}
        distinct: dict[Any, dict[str, set]] = {}
        sums = [f for f in SUM_FIELDS[tool] if f not in DISTINCT]
        for r in rows:
            key = r.get(GROUP_FIELDS[group_by]) if group_by else None
            if group_by == "date" and key is not None:
                key = key.isoformat()
            g = groups.setdefault(key, {group_by: key} if group_by else {})
            for f in sums:
                if f in r and r[f] is not None:
                    g[f] = round(g.get(f, 0) + r[f], 2)
            for out, src in DISTINCT.items():
                if out in SUM_FIELDS[tool] and src in r and r[src] not in (None, ""):
                    distinct.setdefault(key, {}).setdefault(out, set()).add(r[src])
        out = []
        for key, g in groups.items():
            for f, vals in distinct.get(key, {}).items():
                g[f] = len(vals)
            for f, v in list(g.items()):
                if isinstance(v, float) and v.is_integer() and f != "weight_kg":
                    g[f] = int(v)
            out.append(g)
        if group_by:
            out.sort(key=lambda x: str(x.get(group_by)))
        return out

    # ---- interface ------------------------------------------------------------------------
    async def run_tool(self, tool: str, params: dict[str, Any]) -> ToolResult:
        spec = self.specs.get(tool)
        if spec is None:
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"No API configured for {tool} in data_apis.yaml")
        if not self._codes:
            await self.master_data()
        started = time.perf_counter()
        query = {}
        p = dict(params)
        for ours, theirs in spec.params.items():
            v = params.get(ours)
            if v is not None:
                query[theirs] = v.strftime(self.date_format) if isinstance(v, date) else v
        body = await self._call(spec.url, spec.method, self._headers(spec.api_key_env, spec.auth_header), query)
        raw_rows = _dig(body, spec.rows_path)
        if not isinstance(raw_rows, list):
            raise DataSourceError("DATA_SOURCE_UNAVAILABLE", f"{spec.url}: rows are not a list")
        rows = [self._normalize(r, spec) for r in raw_rows if isinstance(r, dict)]
        rows = [r for r in rows if self._matches(r, p)]
        out = self._aggregate(tool, rows, params.get("group_by"))
        # V3 needs real dates in rows only when grouping by date; summary rows carry no date key.
        sent = {k: iso(v) for k, v in params.items()}
        return ToolResult(tool=tool, ok=True, params=sent, applied_filters=sent, rows=out, row_count=len(out),
                          source_ref=f"rest:{spec.method} {spec.url}",
                          duration_ms=int((time.perf_counter() - started) * 1000))

    async def master_data(self) -> MasterData:
        md = self.cfg.get("master_data") or {}
        result = MasterData()
        for kind in ("paper_types", "customers", "warehouses"):
            src = md.get(kind) or {}
            items: list[MasterItem] = []
            if src.get("url"):
                body = await self._call(src["url"], "GET", self._headers(src.get("api_key_env"),
                                        src.get("auth_header", "X-API-Key")), {})
                for x in _dig(body, src.get("rows_path", "")):
                    items.append(MasterItem(str(x[src["code_field"]]), str(x[src["name_field"]])))
            for x in src.get("static") or []:
                items.append(MasterItem(str(x["code"]), str(x["name"])))
            setattr(result, kind, items)
        self._codes = {}
        for item in result.paper_types:
            self._codes[item.code.lower()] = item.code
            self._codes[item.name.lower()] = item.code
        return result

    async def health(self) -> bool:
        try:
            await self.master_data()
            return bool(self.specs)
        except DataSourceError:
            return False
