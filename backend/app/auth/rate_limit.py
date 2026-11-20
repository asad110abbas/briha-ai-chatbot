"""Postgres-backed rate limit (SPEC G3): counts the user's saved questions, so it works across workers."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Conversation, Message, User, utcnow
from app.errors import ApiError


async def _count_since(db: AsyncSession, user: User, delta: timedelta) -> int:
    q = (
        select(func.count())
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == user.id, Message.role == "user", Message.created_at >= utcnow() - delta)
    )
    return int(await db.scalar(q) or 0)


async def enforce_rate_limit(db: AsyncSession, user: User) -> None:
    s = get_settings()
    if await _count_since(db, user, timedelta(minutes=1)) >= s.rate_limit_per_minute:
        raise ApiError("RATE_LIMITED", 429)
    if await _count_since(db, user, timedelta(days=1)) >= s.rate_limit_per_day:
        raise ApiError("RATE_LIMITED", 429, "Daily question limit reached. Please try again tomorrow.")
