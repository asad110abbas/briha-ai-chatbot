import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import check_origin, current_user
from app.db.models import Conversation, Feedback, Message, User, utcnow
from app.db.session import get_db
from app.errors import ApiError

router = APIRouter(prefix="/api", tags=["conversations"], dependencies=[Depends(check_origin)])


class ConversationIn(BaseModel):
    title: str | None = None


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=1000)


async def owned_conversation(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id or conv.deleted_at is not None:
        raise ApiError("NOT_FOUND", 404)
    return conv


def message_out(m: Message) -> dict:
    ui = dict(m.ui_payload or {})
    ui.pop("pending_plan", None)
    ui.pop("context", None)
    return {"id": str(m.id), "role": m.role, "content": m.content, "language": m.language, "status": m.status,
            "ui_payload": ui, "created_at": m.created_at.isoformat()}


@router.get("/conversations")
async def list_conversations(cursor: str | None = None, limit: int = Query(30, ge=1, le=100),
                             user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    q = select(Conversation).where(Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
    if cursor:
        q = q.where(Conversation.updated_at < datetime.fromisoformat(cursor))
    items = (await db.scalars(q.order_by(Conversation.updated_at.desc()).limit(limit + 1))).all()
    next_cursor = items[limit - 1].updated_at.isoformat() if len(items) > limit else None
    return {"items": [{"id": str(c.id), "title": c.title, "updated_at": c.updated_at.isoformat()}
                      for c in items[:limit]], "next_cursor": next_cursor}


@router.post("/conversations", status_code=201)
async def create_conversation(body: ConversationIn, user: User = Depends(current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = Conversation(user_id=user.id, title=(body.title or "New chat")[:120])
    db.add(conv)
    await db.commit()
    return {"id": str(conv.id), "title": conv.title}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: uuid.UUID, user: User = Depends(current_user),
                        db: AsyncSession = Depends(get_db)):
    await owned_conversation(db, user, conversation_id)
    msgs = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                             .order_by(Message.created_at))).all()
    ratings = dict((await db.execute(select(Feedback.message_id, Feedback.rating).where(
        Feedback.user_id == user.id, Feedback.message_id.in_([m.id for m in msgs])))).all()) if msgs else {}
    out = []
    for m in msgs:
        item = message_out(m)
        item["rating"] = ratings.get(m.id)
        out.append(item)
    return {"items": out}


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: uuid.UUID, body: ConversationPatch,
                              user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conv = await owned_conversation(db, user, conversation_id)
    conv.title = body.title.strip()
    await db.commit()
    return {"id": str(conv.id), "title": conv.title}


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, user: User = Depends(current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = await owned_conversation(db, user, conversation_id)
    conv.deleted_at = utcnow()
    await db.commit()
    return Response(status_code=204)


@router.post("/messages/{message_id}/feedback", status_code=204)
async def give_feedback(message_id: uuid.UUID, body: FeedbackIn, user: User = Depends(current_user),
                        db: AsyncSession = Depends(get_db)):
    if body.rating == 0:
        raise ApiError("INPUT_INVALID", 422, "Rating must be 1 or -1.")
    msg = await db.get(Message, message_id)
    if msg is None or msg.role != "assistant":
        raise ApiError("NOT_FOUND", 404)
    await owned_conversation(db, user, msg.conversation_id)
    fb = await db.scalar(select(Feedback).where(Feedback.message_id == message_id, Feedback.user_id == user.id))
    if fb is None:
        db.add(Feedback(message_id=message_id, user_id=user.id, rating=body.rating, comment=body.comment))
    else:
        fb.rating, fb.comment = body.rating, body.comment
    await db.commit()
    return Response(status_code=204)
