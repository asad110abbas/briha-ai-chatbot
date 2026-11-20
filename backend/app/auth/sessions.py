import base64
import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Session, User, aware, utcnow

COOKIE_NAME = "briha_session"
_TOUCH_INTERVAL = timedelta(minutes=5)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db: AsyncSession, user: User, ip: str | None, user_agent: str | None) -> str:
    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    now = utcnow()
    db.add(Session(
        user_id=user.id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=get_settings().session_absolute_days),
        ip=ip,
        user_agent=(user_agent or "")[:500],
    ))
    return token


async def lookup_session(db: AsyncSession, token: str) -> tuple[Session, User] | None:
    row = (await db.execute(
        select(Session, User).join(User, User.id == Session.user_id).where(Session.token_hash == hash_token(token))
    )).first()
    if row is None:
        return None
    session, user = row
    now = utcnow()
    idle = timedelta(hours=get_settings().session_idle_hours)
    if (
        session.revoked_at is not None
        or aware(session.expires_at) <= now
        or aware(session.last_seen_at) + idle <= now
        or not user.is_active
    ):
        return None
    if aware(session.last_seen_at) + _TOUCH_INTERVAL <= now:
        session.last_seen_at = now
        await db.commit()
    return session, user


async def revoke_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None)).values(revoked_at=utcnow())
    )
