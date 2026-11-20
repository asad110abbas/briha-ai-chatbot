"""Master data (from the data source, cached) + glossary aliases (from BRIHA's DB)."""

import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasources.base import DataSource, MasterData
from app.db.models import GlossaryTerm


@dataclass
class Glossary:
    by_kind: dict[str, dict[str, str]] = field(default_factory=dict)  # kind -> alias(lower) -> canonical

    def kind(self, kind: str) -> dict[str, str]:
        return self.by_kind.get(kind, {})


async def load_glossary(db: AsyncSession) -> Glossary:
    g = Glossary()
    for term in (await db.scalars(select(GlossaryTerm))).all():
        g.by_kind.setdefault(term.kind, {})[term.alias.strip().lower()] = term.canonical_value
    return g


class MasterCache:
    def __init__(self, ds: DataSource, ttl_hours: float):
        self._ds = ds
        self._ttl = ttl_hours * 3600
        self._data: MasterData | None = None
        self._loaded_at = 0.0

    async def get(self) -> MasterData:
        if self._data is None or time.monotonic() - self._loaded_at > self._ttl:
            self._data = await self._ds.master_data()
            self._loaded_at = time.monotonic()
        return self._data

    def invalidate(self) -> None:
        self._data = None
