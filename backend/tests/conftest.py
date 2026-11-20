import json
import os
import re
from collections.abc import Callable
from typing import Any

os.environ["FIXED_TODAY"] = "2026-11-03"  # Tuesday; matches SPEC §5/§16
os.environ["APP_ENV"] = "test"
os.environ["DATASOURCE_MODE"] = "mock"
os.environ["MOCK_FAULTS"] = ""
os.environ["VALIDATOR_LLM_ENABLED"] = "true"
os.environ["ADMIN_USERNAME"] = ""

import httpx
import pytest

from app.auth.passwords import hash_password
from app.config import get_settings
from app.datasources.mock import MockDataSource
from app.db import session as db_session
from app.db.models import Base, User
from app.db.seed import seed_glossary
from app.llm.client import LLMError, Usage
from app.main import create_app
from app.pipeline.schemas import JudgeVerdict, QueryPlan

ORIGIN = "http://test"  # same origin as the test client base_url


def make_plan(language="english", intent="data_query", metrics=(), tools=(), date="today", n=None,
              from_date=None, to_date=None, paper_type=None, gsm=None, size=None, customer=None, warehouse=None,
              group_by=None, unit=None, clarification=None, reply_language=None) -> QueryPlan:
    return QueryPlan.model_validate({
        "language": language, "reply_language": reply_language, "intent": intent, "metrics": list(metrics), "tool_calls": list(tools),
        "filters": {"date": {"expression": date, "n": n, "from_date": from_date, "to_date": to_date},
                    "paper_type": paper_type, "gsm": gsm, "size": size, "customer": customer,
                    "warehouse": warehouse},
        "quantity_unit": unit, "group_by": group_by, "clarification": clarification,
        "assumptions": [], "confidence": 0.9,
    })


class FakeLLM:
    """Scripted stand-in for GPT-5. `planner(payload) -> QueryPlan`; responder writes a grounded answer."""

    def __init__(self):
        self.planner: Callable[[dict], QueryPlan] | None = None
        self.judge: Callable[[dict], JudgeVerdict] = lambda d: JudgeVerdict(
            verdict="pass", issue=None, explanation="ok", fix_hint=None)
        self.bad_number_answers = 0  # how many responder answers should contain an invented number
        self.fail_all = False
        self.chat_replies: list[str] = []  # scripted conversation-agent replies, used in order
        self.calls: list[tuple[str, Any]] = []

    async def parse(self, *, model, system, user, schema):
        if self.fail_all:
            raise LLMError("down")
        if schema is QueryPlan:
            payload = json.loads(user)
            self.calls.append(("plan", payload))
            assert self.planner, "test must set llm.planner"
            return self.planner(payload), Usage(100, 50)
        data = json.loads(re.search(r"<data>\n(.*)\n</data>", user, re.DOTALL).group(1))
        self.calls.append(("judge", data))
        return self.judge(data), Usage(80, 20)

    async def text(self, *, model, system, user):
        if self.fail_all:
            raise LLMError("down")
        data = json.loads(re.search(r"<data>\n(.*)\n</data>", user, re.DOTALL).group(1))
        if "facts" not in data:  # conversation agent: no tool data, only the chat
            self.calls.append(("converse", data))
            return self.chat_replies.pop(0) if self.chat_replies else "Okay.", Usage(40, 10)
        self.calls.append(("respond", data))
        parts = [f"**{v:,}** {k}" for k, v in data["facts"].items()]
        text = f"{data['date_label']}: " + (", ".join(parts) if parts else "nothing recorded")
        if self.bad_number_answers > 0:
            self.bad_number_answers -= 1
            text += " (about 99,999 total)"
        return text, Usage(60, 40)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def mock_ds() -> MockDataSource:
    return MockDataSource(get_settings().today)


@pytest.fixture
async def app(tmp_path, fake_llm, mock_ds):
    engine = db_session.init_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db_session.sessionmaker()() as db:
        await seed_glossary(db)
        db.add_all([
            User(username="admin", full_name="Admin User", password_hash=hash_password("adminpass1"), role="admin",
                 can_view_financials=True),
            User(username="hamza", full_name="Hamza Khan", password_hash=hash_password("userpass1"), role="user",
                 can_view_financials=False),
        ])
        await db.commit()
    application = create_app(llm=fake_llm, datasource=mock_ds, run_startup=False)
    yield application
    await engine.dispose()


async def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                             headers={"Origin": ORIGIN})


async def login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture
async def user_client(app):
    async with await _client(app) as c:
        r = await login(c, "hamza", "userpass1")
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
async def admin_client(app):
    async with await _client(app) as c:
        r = await login(c, "admin", "adminpass1")
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
async def anon_client(app):
    async with await _client(app) as c:
        yield c


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


async def ask(client: httpx.AsyncClient, message: str, conversation_id: str | None = None) -> dict:
    r = await client.post("/api/chat", json={"message": message, "conversation_id": conversation_id})
    assert r.status_code == 200, r.text
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    final = events[-1]
    return {"events": events, "names": names, "final": final[0], "data": final[1],
            "text": "".join(d["text"] for e, d in events if e == "delta"),
            "conversation_id": events[0][1]["conversation_id"]}
