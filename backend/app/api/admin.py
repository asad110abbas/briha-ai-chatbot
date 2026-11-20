import uuid
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.auth import user_out
from app.auth.deps import check_origin, client_ip, require_admin
from app.auth.passwords import hash_password, password_ok
from app.auth.sessions import revoke_user_sessions
from app.config import get_settings
from app.db.models import GLOSSARY_KINDS, AuditLog, Feedback, GlossaryTerm, Message, QueryRun, User, utcnow
from app.db.session import get_db
from app.errors import ApiError

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(check_origin)])


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    password: str
    can_view_financials: bool = False
    must_change_password: bool = False


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    can_view_financials: bool | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str
    must_change_password: bool = False


class GlossaryIn(BaseModel):
    kind: str
    alias: str = Field(min_length=1, max_length=100)
    canonical_value: str = Field(min_length=1, max_length=100)
    notes: str | None = None


def admin_user_out(u: User) -> dict:
    return {**user_out(u), "is_active": u.is_active,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat()}


# ---- users ------------------------------------------------------------------------------------
@router.get("/users")
async def list_users(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    users = (await db.scalars(select(User).order_by(User.created_at))).all()
    return {"items": [admin_user_out(u) for u in users]}


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, request: Request, admin: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    if not password_ok(body.password, body.username):
        raise ApiError("PASSWORD_WEAK", 400)
    exists = await db.scalar(select(User.id).where(func.lower(User.username) == body.username.lower()))
    if exists:
        raise ApiError("USERNAME_TAKEN", 409)
    user = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password),
                role="user",  # single-admin policy: accounts created here are never admins
                can_view_financials=body.can_view_financials,
                must_change_password=body.must_change_password, created_by=admin.id)
    db.add(user)
    await db.flush()
    db.add(AuditLog(actor_user_id=admin.id, action="user_created", target_type="user", target_id=str(user.id),
                    details={"username": user.username, "role": user.role}, ip=client_ip(request)))
    await db.commit()
    return admin_user_out(user)


@router.patch("/users/{user_id}")
async def update_user(user_id: uuid.UUID, body: UserPatch, request: Request, admin: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if user is None:
        raise ApiError("NOT_FOUND", 404)
    changes = body.model_dump(exclude_none=True)
    if user.id == admin.id and changes.get("is_active") is False:
        raise ApiError("FORBIDDEN", 403, "You can't disable your own account.")
    for k, v in changes.items():
        setattr(user, k, v)
    if changes.get("is_active") is False:
        await revoke_user_sessions(db, user.id)
    db.add(AuditLog(actor_user_id=admin.id, action="user_disabled" if changes.get("is_active") is False
                    else "user_updated", target_type="user", target_id=str(user.id), details=changes,
                    ip=client_ip(request)))
    await db.commit()
    return admin_user_out(user)


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_password(user_id: uuid.UUID, body: PasswordReset, request: Request,
                         admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if user is None:
        raise ApiError("NOT_FOUND", 404)
    if not password_ok(body.new_password, user.username):
        raise ApiError("PASSWORD_WEAK", 400)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = body.must_change_password
    user.failed_login_count, user.locked_until = 0, None
    await revoke_user_sessions(db, user.id)
    db.add(AuditLog(actor_user_id=admin.id, action="password_reset", target_type="user", target_id=str(user.id),
                    ip=client_ip(request)))
    await db.commit()
    return Response(status_code=204)


# ---- glossary ---------------------------------------------------------------------------------
@router.get("/glossary")
async def list_glossary(kind: str | None = None, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    q = select(GlossaryTerm).order_by(GlossaryTerm.kind, GlossaryTerm.alias)
    if kind:
        q = q.where(GlossaryTerm.kind == kind)
    return {"items": [{"id": str(g.id), "kind": g.kind, "alias": g.alias, "canonical_value": g.canonical_value,
                       "notes": g.notes} for g in (await db.scalars(q)).all()]}


@router.post("/glossary", status_code=201)
async def add_glossary(body: GlossaryIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if body.kind not in GLOSSARY_KINDS:
        raise ApiError("INPUT_INVALID", 422, f"kind must be one of {GLOSSARY_KINDS}")
    term = GlossaryTerm(kind=body.kind, alias=body.alias.strip(), canonical_value=body.canonical_value.strip(),
                        notes=body.notes, created_by=admin.id)
    db.add(term)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ApiError("ALIAS_EXISTS", 409) from None
    db.add(AuditLog(actor_user_id=admin.id, action="glossary_created", target_type="glossary",
                    target_id=str(term.id), details=body.model_dump()))
    await db.commit()
    return {"id": str(term.id), "kind": term.kind, "alias": term.alias, "canonical_value": term.canonical_value,
            "notes": term.notes}


@router.delete("/glossary/{term_id}", status_code=204)
async def delete_glossary(term_id: uuid.UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    term = await db.get(GlossaryTerm, term_id)
    if term is None:
        raise ApiError("NOT_FOUND", 404)
    db.add(AuditLog(actor_user_id=admin.id, action="glossary_deleted", target_type="glossary",
                    target_id=str(term.id), details={"alias": term.alias, "canonical_value": term.canonical_value}))
    await db.delete(term)
    await db.commit()
    return Response(status_code=204)


# ---- query log --------------------------------------------------------------------------------
def _range(from_: date | None, to: date | None) -> tuple[datetime, datetime]:
    tz = get_settings().tz
    # Logs use the real calendar date (FIXED_TODAY only affects how questions are answered).
    today = max(get_settings().today(), datetime.now(tz).date())
    start = datetime.combine(from_ or today - timedelta(days=30), time.min, tz)
    end = datetime.combine((to or today) + timedelta(days=1), time.min, tz)
    return start, end


@router.get("/runs")
async def list_runs(status: str | None = None, user_id: uuid.UUID | None = None,
                    from_: date | None = Query(None, alias="from"), to: date | None = None,
                    rating: int | None = None, limit: int = Query(50, ge=1, le=200), deleted: bool = False,
                    _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """`deleted=false` (default) is the normal log; `deleted=true` lists only the entries an admin deleted."""
    start, end = _range(from_, to)
    deleter = aliased(User)
    q = (select(QueryRun, Message.content, User.username, Feedback.rating, deleter.username)
         .join(Message, Message.id == QueryRun.user_message_id)
         .join(User, User.id == QueryRun.user_id)
         .outerjoin(Feedback, Feedback.message_id == QueryRun.assistant_message_id)
         .outerjoin(deleter, deleter.id == QueryRun.deleted_by)
         .where(QueryRun.created_at >= start, QueryRun.created_at < end)
         .where(QueryRun.deleted_at.is_not(None) if deleted else QueryRun.deleted_at.is_(None)))
    if status:
        q = q.where(QueryRun.final_status == status)
    if user_id:
        q = q.where(QueryRun.user_id == user_id)
    if rating is not None:
        q = q.where(Feedback.rating == rating)
    rows = (await db.execute(q.order_by(QueryRun.created_at.desc()).limit(limit))).all()
    return {"items": [{
        "id": str(r.id), "created_at": r.created_at.isoformat(), "username": username, "question": question,
        "status": r.final_status, "error_code": r.error_code, "attempts": r.attempts,
        "total_latency_ms": r.total_latency_ms, "cost_usd": float(r.estimated_cost_usd), "rating": rt,
        "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None, "deleted_by": deleted_by,
    } for r, question, username, rt, deleted_by in rows], "next_cursor": None}


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    run = await db.get(QueryRun, run_id)
    if run is None:
        raise ApiError("NOT_FOUND", 404)
    user_msg = await db.get(Message, run.user_message_id)
    answer = await db.get(Message, run.assistant_message_id) if run.assistant_message_id else None
    user = await db.get(User, run.user_id)
    cols = {c.name: getattr(run, c.name) for c in QueryRun.__table__.columns}
    cols = {k: (str(v) if isinstance(v, uuid.UUID) else v.isoformat() if isinstance(v, datetime) else v)
            for k, v in cols.items()}
    cols["estimated_cost_usd"] = float(run.estimated_cost_usd)
    deleter = await db.get(User, run.deleted_by) if run.deleted_by else None
    return {**cols, "username": user.username if user else None,
            "question": user_msg.content if user_msg else None,
            "answer": answer.content if answer else None,
            "deleted_by_username": deleter.username if deleter else None}


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: uuid.UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Soft delete: hide the entry from the query log and record who deleted it and when.

    Nothing is erased here. The user's chat is untouched, and the row is removed for good by the nightly
    retention job once it is RETENTION_MONTHS old, like every other log entry.
    """
    run = await db.get(QueryRun, run_id)
    if run is None:
        raise ApiError("NOT_FOUND", 404)
    if run.deleted_at is None:
        asker = await db.get(User, run.user_id)
        run.deleted_at, run.deleted_by = utcnow(), admin.id
        db.add(AuditLog(actor_user_id=admin.id, action="run_deleted", target_type="query_run", target_id=str(run.id),
                        details={"username": asker.username if asker else None, "status": run.final_status,
                                 "asked_at": run.created_at.isoformat()}))
        await db.commit()
    return Response(status_code=204)


@router.get("/stats")
async def stats(from_: date | None = Query(None, alias="from"), to: date | None = None,
                _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    start, end = _range(from_, to)
    runs = (await db.execute(select(QueryRun.final_status, QueryRun.total_latency_ms, QueryRun.estimated_cost_usd,
                                    QueryRun.created_at).where(QueryRun.created_at >= start,
                                                               QueryRun.created_at < end))).all()
    n = len(runs)

    def pct(status: str) -> float:
        return round(100 * sum(1 for r in runs if r[0] == status) / n, 1) if n else 0.0

    lat = sorted(r[1] for r in runs if r[1] is not None)

    def p(q: float) -> int | None:
        return lat[min(len(lat) - 1, int(q * len(lat)))] if lat else None

    failed = (await db.execute(
        select(Message.content, func.count()).join(QueryRun, QueryRun.user_message_id == Message.id)
        .where(QueryRun.created_at >= start, QueryRun.created_at < end,
               QueryRun.final_status.in_(["no_data", "error"]))
        .group_by(Message.content).order_by(func.count().desc()).limit(10))).all()
    active_users = await db.scalar(select(func.count(func.distinct(QueryRun.user_id)))
                                   .where(QueryRun.created_at >= start, QueryRun.created_at < end))
    thumbs_down = await db.scalar(select(func.count()).select_from(Feedback).where(
        Feedback.rating == -1, Feedback.created_at >= start, Feedback.created_at < end))
    return {
        "questions": n, "active_users": active_users or 0,
        "answered_pct": pct("answered"), "clarification_pct": pct("clarification"),
        "no_data_pct": pct("no_data"), "error_pct": pct("error"), "refused_pct": pct("refused"),
        "p50_ms": p(0.5), "p95_ms": p(0.95),
        "cost_usd": round(sum(float(r[2]) for r in runs), 4),
        "thumbs_down": thumbs_down or 0,
        "top_failed": [{"question": q, "count": c} for q, c in failed],
    }
