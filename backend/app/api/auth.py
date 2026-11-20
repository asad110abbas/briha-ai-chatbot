
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import check_origin, client_ip, current_user
from app.auth.passwords import hash_password, password_ok, verify_password
from app.auth.sessions import COOKIE_NAME, create_session, hash_token, revoke_user_sessions
from app.config import get_settings
from app.db.models import AuditLog, Session, User, utcnow
from app.db.session import get_db
from app.errors import ApiError

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(check_origin)])


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


def user_out(u: User) -> dict:
    return {"id": str(u.id), "username": u.username, "full_name": u.full_name, "role": u.role,
            "can_view_financials": u.can_view_financials, "must_change_password": u.must_change_password}


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    ip = client_ip(request)
    user = await db.scalar(select(User).where(func.lower(User.username) == body.username.strip().lower()))
    now = utcnow()
    if user is None or not user.is_active:
        db.add(AuditLog(action="login_failed", details={"username": body.username[:100]}, ip=ip))
        await db.commit()
        raise ApiError("AUTH_INVALID", 401)
    # No lockout (owner's decision, 2026-11-04): wrong passwords are only counted and audit-logged.
    if not verify_password(user.password_hash, body.password):
        user.failed_login_count += 1
        db.add(AuditLog(actor_user_id=user.id, action="login_failed", ip=ip))
        await db.commit()
        raise ApiError("AUTH_INVALID", 401)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    token = await create_session(db, user, ip, request.headers.get("user-agent"))
    db.add(AuditLog(actor_user_id=user.id, action="login_success", ip=ip))
    await db.commit()
    s = get_settings()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=s.cookie_secure, samesite="lax", path="/",
                        max_age=s.session_absolute_days * 86400)
    return {"user": user_out(user)}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session = await db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
        if session and session.revoked_at is None:
            session.revoked_at = utcnow()
            db.add(AuditLog(actor_user_id=session.user_id, action="logout"))
            await db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/change-password", status_code=204)
async def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError("AUTH_INVALID", 401, "Current password is incorrect.")
    if not password_ok(body.new_password, user.username):
        raise ApiError("PASSWORD_WEAK", 400)
    user = await db.merge(user)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    # keep this session, revoke the others
    token = request.cookies.get(COOKIE_NAME, "")
    await revoke_user_sessions(db, user.id)
    current = await db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if current:
        current.revoked_at = None
    db.add(AuditLog(actor_user_id=user.id, action="password_changed", target_type="user", target_id=str(user.id)))
    await db.commit()
    return Response(status_code=204)
