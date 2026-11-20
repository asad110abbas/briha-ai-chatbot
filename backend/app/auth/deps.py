from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import COOKIE_NAME, lookup_session
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.errors import ApiError


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError("AUTH_REQUIRED", 401)
    found = await lookup_session(db, token)
    if found is None:
        raise ApiError("AUTH_REQUIRED", 401)
    return found[1]


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise ApiError("FORBIDDEN", 403)
    return user


def check_origin(request: Request) -> None:
    """SPEC S6: state-changing requests must come from the page BRIHA itself served (same origin)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    settings = get_settings()
    if origin is None:
        if settings.app_env == "production":
            raise ApiError("ORIGIN_INVALID", 403)
        return
    origin_host = urlsplit(origin).netloc.lower()
    same_origin = origin_host == (request.headers.get("host") or "").lower()
    configured = origin.rstrip("/") == settings.app_base_url.rstrip("/")
    if not (same_origin or configured):
        raise ApiError("ORIGIN_INVALID", 403)
