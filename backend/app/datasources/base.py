"""DataSource interface (TRD §3.1). Read-only by design: there are no write methods (SPEC R6)."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.pipeline.resolve.entities import MasterItem
from app.pipeline.schemas import ToolResult


class DataSourceError(Exception):
    def __init__(self, code: str, detail: str = ""):  # DATA_SOURCE_UNAVAILABLE | DATA_SOURCE_TIMEOUT
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class MasterData:
    paper_types: list[MasterItem] = field(default_factory=list)
    customers: list[MasterItem] = field(default_factory=list)
    warehouses: list[MasterItem] = field(default_factory=list)


class DataSource(Protocol):
    mode: str

    async def run_tool(self, tool: str, params: dict[str, Any]) -> ToolResult: ...
    async def master_data(self) -> MasterData: ...
    async def health(self) -> bool: ...


def iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v
