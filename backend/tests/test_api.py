"""API + pipeline acceptance tests (SPEC §16), against mock data with today fixed to 2026-11-03."""

import uuid

from sqlalchemy import select

from app.config import get_settings
from app.db import session as db_session
from app.db.models import QueryRun
from app.pipeline.schemas import JudgeVerdict
from tests.conftest import _client, ask, login, make_plan

CUT_SALES = {"metrics": ["sheets_cut", "quantity_sold"], "tools": ["get_cutting_summary", "get_sales_summary"]}


# ---- auth -------------------------------------------------------------------------------------
async def test_login_me_logout(user_client):
    me = (await user_client.get("/api/auth/me")).json()
    assert me["username"] == "hamza" and me["role"] == "user"
    assert (await user_client.post("/api/auth/logout")).status_code == 204
    assert (await user_client.get("/api/auth/me")).status_code == 401


async def test_login_errors_are_generic(anon_client):
    a = await login(anon_client, "nobody", "whatever1")
    b = await login(anon_client, "hamza", "wrongpass1")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"] == "AUTH_INVALID"


async def test_no_lockout_after_many_failures(anon_client):  # AT-15 changed: lockout removed
    for _ in range(10):
        assert (await login(anon_client, "hamza", "wrong-pass")).json()["error"]["code"] == "AUTH_INVALID"
    r = await login(anon_client, "hamza", "userpass1")  # correct password still works
    assert r.status_code == 200, r.text


async def test_user_cannot_use_admin_api(user_client):  # AT-19
    r = await user_client.get("/api/admin/users")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_disabled_user_is_logged_out(admin_client, user_client):  # AT-20
    users = (await admin_client.get("/api/admin/users")).json()["items"]
    hamza = next(u for u in users if u["username"] == "hamza")
    assert (await admin_client.patch(f"/api/admin/users/{hamza['id']}", json={"is_active": False})).status_code == 200
    r = await user_client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_admin_creates_user_and_resets_password(admin_client, anon_client):
    r = await admin_client.post("/api/admin/users", json={
        "username": "director", "full_name": "Director Sahab", "password": "secret123", "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "user"  # single-admin policy: never an admin
    assert (await admin_client.post("/api/admin/users", json={
        "username": "Director", "full_name": "x", "password": "secret123"})).status_code == 409
    assert (await admin_client.post("/api/admin/users", json={
        "username": "weak", "full_name": "x", "password": "123"})).json()["error"]["code"] == "PASSWORD_WEAK"
    uid = r.json()["id"]
    assert (await admin_client.post(f"/api/admin/users/{uid}/reset-password",
                                    json={"new_password": "newsecret9"})).status_code == 204
    assert (await login(anon_client, "director", "newsecret9")).status_code == 200


async def test_user_cannot_touch_another_users_chat(admin_client, user_client, anon_client, fake_llm):
    # hamza has a chat with one answered message
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "How many sheets were cut today?")
    conv_id, msg_id = res["conversation_id"], res["data"]["message_id"]

    # a second ordinary user, bilal, signs in
    r = await admin_client.post("/api/admin/users", json={
        "username": "bilal", "full_name": "Bilal", "password": "bilalpass1"})
    assert r.status_code == 201
    assert (await login(anon_client, "bilal", "bilalpass1")).status_code == 200
    bilal = anon_client

    # bilal cannot see, read, rename, delete, rate or post into hamza's chat
    assert conv_id not in [c["id"] for c in (await bilal.get("/api/conversations")).json()["items"]]
    assert (await bilal.get(f"/api/conversations/{conv_id}/messages")).status_code == 404
    assert (await bilal.patch(f"/api/conversations/{conv_id}", json={"title": "hacked"})).status_code == 404
    assert (await bilal.delete(f"/api/conversations/{conv_id}")).status_code == 404
    assert (await bilal.post(f"/api/messages/{msg_id}/feedback", json={"rating": -1})).status_code == 404
    assert (await bilal.post("/api/chat", json={"message": "hi", "conversation_id": conv_id})).status_code == 404

    # hamza's chat is untouched
    items = (await user_client.get("/api/conversations")).json()["items"]
    mine = next(c for c in items if c["id"] == conv_id)
    assert mine["title"] != "hacked"
    msgs = (await user_client.get(f"/api/conversations/{conv_id}/messages")).json()["items"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["rating"] is None


async def test_change_password(user_client, anon_client):
    r = await user_client.post("/api/auth/change-password",
                               json={"current_password": "userpass1", "new_password": "brandnew99"})
    assert r.status_code == 204
    assert (await user_client.get("/api/auth/me")).status_code == 200  # current session kept
    assert (await login(anon_client, "hamza", "brandnew99")).status_code == 200


async def test_origin_check(user_client):
    r = await user_client.post("/api/conversations", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


async def test_glossary_crud(admin_client):
    r = await admin_client.post("/api/admin/glossary",
                                json={"kind": "paper_type", "alias": "gatta", "canonical_value": "DUPLEX"})
    assert r.status_code == 201
    dup = await admin_client.post("/api/admin/glossary",
                                  json={"kind": "paper_type", "alias": "GATTA", "canonical_value": "DUPLEX"})
    assert dup.status_code == 409
    assert (await admin_client.delete(f"/api/admin/glossary/{r.json()['id']}")).status_code == 204


# ---- chat pipeline ----------------------------------------------------------------------------
async def test_at01_english_cutting_today(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "How many sheets were cut today?")
    assert res["names"][:2] == ["meta", "status"]
    stages = [d["stage"] for e, d in res["events"] if e == "status"]
    assert stages == ["understanding", "retrieving", "validating", "responding"]
    assert res["final"] == "done" and res["data"]["status"] == "answered" and res["data"]["verified"]
    assert res["data"]["language"] == "english"
    assert res["text"].startswith("Today (3 Nov 2026)")
    assert res["data"]["filters"]["Date"] == "3 Nov 2026"


async def test_at02_roman_urdu_cut_and_sold(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", **CUT_SALES)
    res = await ask(user_client, "Aaj kitne papers kate aur kitne bike?")
    assert res["data"]["language"] == "roman_urdu"
    assert res["text"].startswith("Aaj (3 Nov 2026)")
    assert "cutting_total_sheets_cut" in res["text"] and "sales_total_quantity_sheets" in res["text"]
    # financial amounts are stripped for this user (can_view_financials = false)
    respond_data = next(d for kind, d in fake_llm.calls if kind == "respond")
    assert all(r.get("amount_pkr") is None for r in respond_data["rows"]["sales"])
    assert "sales_total_amount_pkr" not in respond_data["facts"]


async def test_at03_at04_filters_resolve_identically(user_client, fake_llm):
    for size in ("23x36", "36 by 23"):
        fake_llm.planner = lambda p, s=size: make_plan(language="roman_urdu", metrics=["quantity_sold"],
                                                       tools=["get_sales_summary"], date="yesterday",
                                                       paper_type="art paper", size=s)
        res = await ask(user_client, f"kal {size} art paper kitna bika")
        f = res["data"]["filters"]
        assert (f["Date"], f["Paper"], f["Size"]) == ("2 Nov 2026", "Art Paper", "23x36")


async def test_at05_follow_up_gets_previous_context(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", **CUT_SALES)
    first = await ask(user_client, "Aaj kitne papers kate aur kitne bike?")

    def follow_up(payload):
        ctx = payload["previous_context"]
        assert ctx["tools"] == CUT_SALES["tools"] and ctx["resolved_filters"]["date_from"] == "2026-11-03"
        return make_plan(language="roman_urdu", metrics=ctx["metrics"], tools=ctx["tools"], date="today",
                         size="23x36")

    fake_llm.planner = follow_up
    res = await ask(user_client, "aur 23x36 ka?", first["conversation_id"])
    assert res["data"]["filters"]["Size"] == "23x36" and res["data"]["status"] == "answered"


async def test_at06_stock(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", metrics=["stock_sheets", "stock_reels"],
                                           tools=["get_stock_summary"], date="none", paper_type="bleach card")
    res = await ask(user_client, "Bleach card ka stock kitna hai?")
    assert res["data"]["filters"]["Stock as of"] == "3 Nov 2026"
    assert res["data"]["filters"]["Paper"] == "Bleach Card"
    assert res["data"]["assumptions"] == []  # no "assumed today" note for stock


async def test_at07_last_month(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", metrics=["quantity_sold"],
                                           tools=["get_sales_summary"], date="last_month")
    res = await ask(user_client, "Pichle mahine ki total sale")
    assert res["data"]["filters"]["Date"] == "1 Oct 2026 – 31 Oct 2026"


async def test_at08_ambiguous_paper_type_and_clarification_flow(user_client, fake_llm):  # AT-08 + AT-17
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", metrics=["stock_sheets"],
                                           tools=["get_stock_summary"], date="none", paper_type="art")
    res = await ask(user_client, "Art ka stock?")
    assert "clarification" in res["names"] and res["data"]["status"] == "clarification"
    assert set(res["data"]["clarification_options"]) >= {"Art Paper", "Art Card"}
    assert not any(kind == "respond" for kind, _ in fake_llm.calls)

    def answer_clarification(payload):
        assert payload["pending_clarification"]["options"] == res["data"]["clarification_options"]
        return make_plan(language="roman_urdu", metrics=["stock_sheets"], tools=["get_stock_summary"],
                         date="none", paper_type="Art Card")

    fake_llm.planner = answer_clarification
    res2 = await ask(user_client, "Art Card", res["conversation_id"])
    assert res2["data"]["filters"]["Paper"] == "Art Card"


async def test_at09_valid_zero(user_client, fake_llm, mock_ds):
    mock_ds.faults = {"empty"}
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"], size="23x36")
    res = await ask(user_client, "How many 23x36 sheets were cut today?")
    assert res["data"]["status"] == "answered" and "nothing recorded" in res["text"]


async def test_at10_datasource_down(user_client, fake_llm, mock_ds):
    mock_ds.faults = {"down"}
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "How many sheets were cut today?")
    assert res["final"] == "error" and res["data"]["code"] == "DATA_SOURCE_UNAVAILABLE"
    assert "delta" not in res["names"]


async def test_at11_at12_refusals(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", intent="write_request")
    res = await ask(user_client, "500 sheets stock mein add kar do")
    assert res["data"]["status"] == "refused" and "change nahi" in res["text"]
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", intent="out_of_scope")
    res = await ask(user_client, "Agle hafte kitna bikega?")
    assert res["data"]["status"] == "refused"
    # a future date that slipped through as data_query is refused by code too
    fake_llm.planner = lambda p: make_plan(metrics=["quantity_sold"], tools=["get_sales_summary"],
                                           date="specific_date", from_date="2026-11-20")
    res = await ask(user_client, "sales on 20 Nov 2026")
    assert res["data"]["status"] == "refused"


async def test_at13_wrong_data_never_shown(user_client, fake_llm, mock_ds):
    mock_ds.faults = {"wrong_dates"}
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "How many sheets were cut today?")
    assert res["data"]["status"] == "no_data" and res["data"]["verified"] is False
    plans = [d for kind, d in fake_llm.calls if kind == "plan"]
    assert len(plans) == 2 and plans[1]["fix_hint"]  # retried once with a fix hint
    assert not any(kind == "respond" for kind, _ in fake_llm.calls)
    async with db_session.sessionmaker()() as db:
        run = (await db.scalars(select(QueryRun))).one()
    assert run.attempts == 2 and run.final_status == "no_data"


async def test_llm_judge_fail_then_pass(user_client, fake_llm):
    verdicts = iter([JudgeVerdict(verdict="fail", issue="wrong_metric", explanation="asked sales",
                                  fix_hint="use get_sales_summary"),
                     JudgeVerdict(verdict="pass", issue=None, explanation="ok", fix_hint=None)])
    fake_llm.judge = lambda d: next(verdicts)
    fake_llm.planner = lambda p: (make_plan(metrics=["quantity_sold"], tools=["get_sales_summary"])
                                  if p["fix_hint"] else make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"]))
    res = await ask(user_client, "How much was sold today?")
    assert res["data"]["status"] == "answered" and "sales_total" in res["text"]


async def test_no_data_messages_are_plain_language(user_client, fake_llm, mock_ds):
    # judge rejects both attempts: the data BRIHA has does not answer the question
    fake_llm.judge = lambda d: JudgeVerdict(verdict="fail", issue="incomplete", explanation="no pending data",
                                            fix_hint="needs pending orders")
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "any cutting stock is in pending")
    assert res["data"]["status"] == "no_data"
    assert "don't have data that answers this question" in res["text"]
    assert "judge" not in res["text"].lower() and "admin can review" not in res["text"]
    # code checks fail (wrong dates from the source): no check ids shown to the user
    fake_llm.judge = lambda d: JudgeVerdict(verdict="pass", issue=None, explanation="ok", fix_hint=None)
    mock_ds.faults = {"wrong_dates"}
    res = await ask(user_client, "How many sheets were cut today?")
    assert res["data"]["status"] == "no_data" and "didn't pass my checks" in res["text"]
    assert "V3" not in res["text"]


async def test_at14_ungrounded_number_falls_back_to_template(user_client, fake_llm):
    fake_llm.bad_number_answers = 2  # both the first answer and the regeneration invent a number
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "How many sheets were cut today?")
    assert "99,999" not in res["text"] and "sheets cut" in res["text"]
    fake_llm.bad_number_answers = 1  # regeneration fixes it
    res = await ask(user_client, "How many sheets were cut today?")
    assert "99,999" not in res["text"] and "cutting_total_sheets_cut" in res["text"]


async def test_at21_rate_limit(user_client, fake_llm, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 3)
    fake_llm.planner = lambda p: make_plan(intent="help")
    for _ in range(3):
        await ask(user_client, "hi")
    r = await user_client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"


async def test_at22_no_date_assumes_today(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", metrics=["sheets_cut"],
                                           tools=["get_cutting_summary"], date="none")
    res = await ask(user_client, "kitne papers kate?")
    assert res["data"]["assumptions"] == ["Date nahi batayi thi, is liye aaj ka data dikhaya hai."]


async def test_at23_financials_visible_only_with_permission(admin_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(metrics=["amount_sold_pkr"], tools=["get_sales_summary"],
                                           date="yesterday")
    await ask(admin_client, "How much was yesterday's sale in rupees?")
    data = next(d for kind, d in fake_llm.calls if kind == "respond")
    assert data["facts"].get("sales_total_amount_pkr", 0) > 0 and data["financials_hidden"] is False


async def test_llm_down(user_client, fake_llm):
    fake_llm.fail_all = True
    res = await ask(user_client, "aaj kitna kata?")
    assert res["final"] == "error" and res["data"]["code"] == "LLM_UNAVAILABLE"


async def test_input_validation(user_client):
    assert (await user_client.post("/api/chat", json={"message": "   "})).status_code == 422
    assert (await user_client.post("/api/chat", json={"message": "x" * 1001})).status_code == 422


async def test_group_by_table_and_history(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"],
                                           date="last_week", group_by="size")
    res = await ask(user_client, "Last week's cutting size wise")
    table = res["data"]["table"]
    assert table["columns"][0] == "Size" and len(table["rows"]) >= 2
    convs = (await user_client.get("/api/conversations")).json()["items"]
    assert convs[0]["title"] == "Last week's cutting size wise"
    msgs = (await user_client.get(f"/api/conversations/{convs[0]['id']}/messages")).json()["items"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert "context" not in msgs[1]["ui_payload"]
    fb = await user_client.post(f"/api/messages/{msgs[1]['id']}/feedback", json={"rating": -1, "comment": "galat"})
    assert fb.status_code == 204


async def test_admin_runs_and_stats(admin_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    await ask(admin_client, "How many sheets were cut today?")
    runs = (await admin_client.get("/api/admin/runs")).json()["items"]
    assert runs[0]["question"] == "How many sheets were cut today?" and runs[0]["status"] == "answered"
    detail = (await admin_client.get(f"/api/admin/runs/{runs[0]['id']}")).json()
    assert detail["tool_calls"][0]["tool"] == "get_cutting_summary" and detail["tokens_input"] > 0
    stats = (await admin_client.get("/api/admin/stats")).json()
    assert stats["questions"] == 1 and stats["answered_pct"] == 100.0


async def test_admin_soft_deletes_a_log_entry(admin_client, user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    first = await ask(user_client, "How many sheets were cut today?")
    conv = first["conversation_id"]
    await ask(user_client, "And how many reels?", conv)
    r = await user_client.post(f"/api/messages/{first['data']['message_id']}/feedback", json={"rating": -1})
    assert r.status_code == 204, r.text

    runs = (await admin_client.get("/api/admin/runs")).json()["items"]
    target = next(x for x in runs if x["question"] == "How many sheets were cut today?")
    assert (await user_client.delete(f"/api/admin/runs/{target['id']}")).status_code == 403  # admins only
    assert (await admin_client.delete(f"/api/admin/runs/{target['id']}")).status_code == 204

    # hidden from the normal log, listed under "deleted" with who and when; deleting twice changes nothing
    left = (await admin_client.get("/api/admin/runs")).json()["items"]
    assert [x["question"] for x in left] == ["And how many reels?"]
    gone = (await admin_client.get("/api/admin/runs", params={"deleted": "true"})).json()["items"]
    assert [x["question"] for x in gone] == ["How many sheets were cut today?"]
    assert gone[0]["deleted_by"] == "admin" and gone[0]["deleted_at"]
    assert (await admin_client.delete(f"/api/admin/runs/{target['id']}")).status_code == 204
    again = (await admin_client.get("/api/admin/runs", params={"deleted": "true"})).json()["items"]
    assert again[0]["deleted_at"] == gone[0]["deleted_at"]
    detail = (await admin_client.get(f"/api/admin/runs/{target['id']}")).json()
    assert detail["deleted_by_username"] == "admin" and detail["question"] == "How many sheets were cut today?"

    # the user's chat is untouched
    msgs = (await user_client.get(f"/api/conversations/{conv}/messages")).json()["items"]
    assert len(msgs) == 4

    from datetime import timedelta

    from app.db.models import AuditLog, utcnow
    from app.main import retention_job

    async with db_session.sessionmaker()() as db:
        audit = (await db.scalars(select(AuditLog).where(AuditLog.action == "run_deleted"))).one()  # logged once
        assert audit.target_id == target["id"] and audit.details["username"] == "hamza"
        # the row is erased for good by the retention job once it is older than RETENTION_MONTHS
        run = await db.get(QueryRun, uuid.UUID(target["id"]))
        run.created_at = utcnow() - timedelta(days=30 * get_settings().retention_months + 1)
        await db.commit()
    await retention_job()
    async with db_session.sessionmaker()() as db:
        assert [str(r.id) for r in (await db.scalars(select(QueryRun))).all()] == [
            x["id"] for x in left]


async def test_health(anon_client):
    body = (await anon_client.get("/api/health")).json()
    assert body["db"] is True and body["datasource"] is True


async def test_roman_urdu_wins_when_model_says_english(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(language="english", intent="out_of_scope")
    res = await ask(user_client, "agle mahine kitna bikega")
    assert res["data"]["language"] == "roman_urdu" and "forecast nahi" in res["text"]


async def test_admin_reset_switch_restores_login(app, monkeypatch):
    from app.db.seed import reset_admin

    async with await _client(app) as c:
        await login(c, "admin", "wrong-pass")

    monkeypatch.setenv("ADMIN_USERNAME", " boss1 ")
    monkeypatch.setenv("ADMIN_PASSWORD", '"NewPass123"')
    get_settings.cache_clear()
    async with db_session.sessionmaker()() as db:
        assert await reset_admin(db) is False  # switch off: nothing changes
    monkeypatch.setenv("ADMIN_RESET_PASSWORD", "true")
    get_settings.cache_clear()
    try:
        async with db_session.sessionmaker()() as db:
            assert await reset_admin(db) is True
        async with await _client(app) as c:
            r = await login(c, "boss1", "NewPass123")
            assert r.status_code == 200, r.text
            assert r.json()["user"]["role"] == "admin"
    finally:
        monkeypatch.delenv("ADMIN_RESET_PASSWORD")
        monkeypatch.setenv("ADMIN_USERNAME", "")
        get_settings.cache_clear()


# ---- conversation: messages about the chat itself ------------------------------------------------
async def test_reply_language_is_remembered(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(intent="conversation", reply_language="english")
    first = await ask(user_client, "from now on answer me in english ok?")
    assert first["data"]["status"] == "answered" and first["data"]["language"] == "english"
    assert first["data"]["content"] == "Sure, I'll answer in English from now on."
    conv = first["conversation_id"]

    # a Roman Urdu question is now answered in English
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", metrics=["sheets_cut"],
                                           tools=["get_cutting_summary"])
    res = await ask(user_client, "aaj kitne papers kate?", conv)
    assert res["data"]["language"] == "english" and res["text"].startswith("Today (3 Nov 2026)")

    # ... and the choice survives further turns, until the user changes it
    res = await ask(user_client, "aur kal?", conv)
    assert res["data"]["language"] == "english"
    # the model repeating the old request is not a new request: no second "Sure, I'll answer in English"
    fake_llm.planner = lambda p: make_plan(intent="conversation", reply_language="english")
    fake_llm.chat_replies = ["Yes, it is read from the data system."]
    res = await ask(user_client, "is this accurate?", conv)
    assert res["data"]["content"] == "Yes, it is read from the data system."
    fake_llm.planner = lambda p: make_plan(language="roman_urdu", intent="conversation",
                                           reply_language="roman_urdu")
    back = await ask(user_client, "ab urdu mein jawab do", conv)
    assert back["data"]["content"] == "Theek hai, ab se main Roman Urdu mein jawab doonga."
    fake_llm.planner = lambda p: make_plan(metrics=["sheets_cut"], tools=["get_cutting_summary"])
    res = await ask(user_client, "How many sheets were cut today?", conv)
    assert res["data"]["language"] == "roman_urdu"


async def test_conversation_question_about_previous_answer(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(metrics=["stock_sheets"], tools=["get_stock_summary"], date="none")
    first = await ask(user_client, "How much stock is left?")
    conv = first["conversation_id"]
    tools_before = sum(1 for kind, _ in fake_llm.calls if kind == "respond")

    fake_llm.planner = lambda p: make_plan(intent="conversation")
    fake_llm.chat_replies = ["These numbers are sample test data as of 3 Nov 2026."]
    res = await ask(user_client, "ok so is this data accurate?", conv)
    assert res["data"]["status"] == "answered" and not res["data"]["verified"]
    assert res["data"]["content"] == "These numbers are sample test data as of 3 Nov 2026."
    assert res["data"]["filters"] is None  # no data query was run again
    assert sum(1 for kind, _ in fake_llm.calls if kind == "respond") == tools_before
    sent = next(d for kind, d in fake_llm.calls if kind == "converse")
    assert sent["history"][0]["content"] == "How much stock is left?" and "sample test data" in sent["data_source"]

    # a data follow-up after the conversational turn still gets the earlier answer's context
    def follow_up(payload):
        assert payload["previous_context"]["tools"] == ["get_stock_summary"]
        return make_plan(metrics=["stock_sheets"], tools=["get_stock_summary"], date="none", size="23x36")

    fake_llm.planner = follow_up
    res = await ask(user_client, "and 23x36?", conv)
    assert res["data"]["filters"]["Size"] == "23x36"


async def test_conversation_reply_never_invents_numbers(user_client, fake_llm):
    fake_llm.planner = lambda p: make_plan(intent="conversation")
    fake_llm.chat_replies = ["About 99,999 sheets I think.", "Still roughly 88,888."]
    res = await ask(user_client, "are you sure about that?")
    assert "99,999" not in res["text"] and "88,888" not in res["text"]
    assert res["text"].startswith("I can't answer that from this chat.")

    fake_llm.chat_replies = ["About 99,999 sheets.", "I can only repeat what is in this chat."]
    res = await ask(user_client, "are you sure?", res["conversation_id"])
    assert res["data"]["content"] == "I can only repeat what is in this chat."  # second try was clean
