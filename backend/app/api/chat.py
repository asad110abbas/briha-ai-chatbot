"""POST /api/chat - Server-Sent Events stream (SPEC §13)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.conversations import owned_conversation
from app.auth.deps import check_origin, current_user
from app.auth.rate_limit import enforce_rate_limit
from app.config import get_settings
from app.db.models import Conversation, Message, QueryRun, User, utcnow
from app.db.session import get_db, sessionmaker
from app.errors import ApiError
from app.pipeline.catalog import load_glossary
from app.pipeline.orchestrator import Orchestrator, RunInput, RunOutcome

router = APIRouter(prefix="/api", tags=["chat"], dependencies=[Depends(check_origin)])
HISTORY_MESSAGES = 6


class ChatIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def chunks(text: str, size: int = 24) -> list[str]:
    words, out, cur = text.split(" "), [], ""
    for w in words:
        cur = f"{cur} {w}" if cur else w
        if len(cur) >= size:
            out.append(cur + " ")
            cur = ""
    if cur:
        out.append(cur)
    return out


async def _context(db: AsyncSession, conversation_id: uuid.UUID, before: Message):
    msgs = (await db.scalars(
        select(Message).where(Message.conversation_id == conversation_id, Message.id != before.id)
        .order_by(Message.created_at.desc()).limit(20)
    )).all()
    history = [{"role": m.role, "content": m.content[:600]} for m in reversed(msgs[:HISTORY_MESSAGES])]
    previous_context = next(
        (m.ui_payload["context"] for m in msgs
         if m.role == "assistant" and m.status == "answered" and m.ui_payload and "context" in m.ui_payload), None)
    pending = None
    last_assistant = next((m for m in msgs if m.role == "assistant"), None)
    if last_assistant and last_assistant.status == "clarification":
        ui = last_assistant.ui_payload or {}
        pending = {"question": last_assistant.content, "options": ui.get("clarification_options"),
                   "original_plan": ui.get("pending_plan")}
    # "answer in English" sticks: every assistant message carries the choice forward in its ui_payload.
    preferred_language = (last_assistant.ui_payload or {}).get("preferred_language") if last_assistant else None
    return history, previous_context, pending, preferred_language


@router.post("/chat")
async def chat(body: ChatIn, request: Request, user: User = Depends(current_user),
               db: AsyncSession = Depends(get_db)):
    s = get_settings()
    message = body.message.strip()
    if not message or len(message) > s.max_message_chars:
        raise ApiError("INPUT_INVALID", 422)
    await enforce_rate_limit(db, user)

    if body.conversation_id:
        conv = await owned_conversation(db, user, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id, title=message[:60])
        db.add(conv)
        await db.flush()
    user_msg = Message(conversation_id=conv.id, role="user", content=message)
    db.add(user_msg)
    conv.updated_at = utcnow()
    await db.commit()

    history, previous_context, pending, preferred_language = await _context(db, conv.id, user_msg)
    glossary = await load_glossary(db)
    orchestrator: Orchestrator = request.app.state.orchestrator
    run_id = uuid.uuid4()
    inp = RunInput(message=message, history=history, previous_context=previous_context,
                   pending_clarification=pending, can_view_financials=user.can_view_financials, glossary=glossary,
                   preferred_language=preferred_language)
    user_id, conv_id, user_msg_id = user.id, conv.id, user_msg.id

    async def stream() -> AsyncIterator[str]:
        yield sse("meta", {"run_id": str(run_id), "conversation_id": str(conv_id),
                           "user_message_id": str(user_msg_id)})
        outcome: RunOutcome | None = None
        try:
            async for event, data in orchestrator.run(inp):
                if event == "outcome":
                    outcome = data
                else:
                    yield sse(event, data)
        except asyncio.CancelledError:
            await asyncio.shield(_save_cancelled(run_id, user_id, conv_id, user_msg_id))
            raise
        assert outcome is not None
        msg_id = await _save(run_id, user_id, conv_id, user_msg_id, outcome)
        if outcome.status == "error":
            yield sse("error", {"code": outcome.error_code or "INTERNAL", "message": outcome.content,
                                "message_id": str(msg_id)})
            return
        if outcome.status != "clarification":
            for part in chunks(outcome.content):
                yield sse("delta", {"text": part})
        ui = outcome.ui_payload
        yield sse("done", {
            "message_id": str(msg_id), "conversation_id": str(conv_id), "status": outcome.status,
            "language": outcome.language, "content": outcome.content, "filters": ui.get("filters"),
            "assumptions": ui.get("assumptions", []), "table": ui.get("table"),
            "clarification_options": ui.get("clarification_options"), "verified": bool(ui.get("verified")),
        })

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _save(run_id: uuid.UUID, user_id, conv_id, user_msg_id, outcome: RunOutcome) -> uuid.UUID:
    s = get_settings()
    async with sessionmaker()() as db:
        msg = Message(conversation_id=conv_id, role="assistant", content=outcome.content,
                      language=outcome.language, status=outcome.status, ui_payload=outcome.ui_payload)
        db.add(msg)
        await db.flush()
        db.add(QueryRun(id=run_id, user_id=user_id, conversation_id=conv_id, user_message_id=user_msg_id,
                        assistant_message_id=msg.id, prompt_version=s.prompt_version,
                        datasource_mode=s.datasource_mode, **outcome.record))
        conv = await db.get(Conversation, conv_id)
        if conv:
            conv.updated_at = utcnow()
        await db.commit()
        return msg.id


async def _save_cancelled(run_id: uuid.UUID, user_id, conv_id, user_msg_id) -> None:
    s = get_settings()
    async with sessionmaker()() as db:
        db.add(QueryRun(id=run_id, user_id=user_id, conversation_id=conv_id, user_message_id=user_msg_id,
                        prompt_version=s.prompt_version, datasource_mode=s.datasource_mode,
                        final_status="error", error_code="CANCELLED"))
        await db.commit()
