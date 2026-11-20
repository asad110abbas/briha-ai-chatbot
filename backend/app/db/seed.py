"""Startup seeding: glossary aliases and the first admin (from .env)."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.config import get_settings
from app.db.models import AuditLog, GlossaryTerm, User

# Deliberately no bare "art" alias: it is ambiguous (Art Paper vs Art Card) and must
# trigger a clarification (SPEC AT-08).
GLOSSARY_SEED: list[tuple[str, str, str]] = [
    ("paper_type", "art paper", "ART_PAPER"),
    ("paper_type", "art card", "ART_CARD"),
    ("paper_type", "bleach", "BLEACH_CARD"),
    ("paper_type", "bleach card", "BLEACH_CARD"),
    ("paper_type", "sbs", "BLEACH_CARD"),
    ("paper_type", "offset", "OFFSET"),
    ("paper_type", "wood free", "OFFSET"),
    ("paper_type", "duplex", "DUPLEX"),
    ("paper_type", "boxboard", "DUPLEX"),
    ("paper_type", "kraft", "KRAFT"),
    ("paper_type", "newsprint", "NEWSPRINT"),
    ("paper_type", "akhbari", "NEWSPRINT"),
    ("unit", "ream", "ream"),
    ("unit", "rim", "ream"),
    ("unit", "sheet", "sheet"),
    ("unit", "papers", "sheet"),
    ("unit", "kaghaz", "sheet"),
]


async def seed_glossary(db: AsyncSession) -> int:
    count = await db.scalar(select(func.count()).select_from(GlossaryTerm))
    if count:
        return 0
    db.add_all(GlossaryTerm(kind=k, alias=a, canonical_value=c) for k, a, c in GLOSSARY_SEED)
    try:
        await db.commit()
    except IntegrityError:  # seeded concurrently by another instance
        await db.rollback()
        return 0
    return len(GLOSSARY_SEED)


async def reset_admin(db: AsyncSession) -> bool:
    """ADMIN_RESET_PASSWORD=true: put the single admin back to the .env username/password, unlocked."""
    s = get_settings()
    if not (s.admin_reset_password and s.admin_username and s.admin_password):
        return False
    admin = await db.scalar(select(User).where(User.role == "admin").order_by(User.created_at).limit(1))
    if admin is None:
        return False
    clash = await db.scalar(select(User).where(func.lower(User.username) == s.admin_username.lower(),
                                               User.id != admin.id))
    if clash is not None:
        return False
    admin.username = s.admin_username
    admin.password_hash = hash_password(s.admin_password)
    admin.is_active = True
    admin.failed_login_count = 0
    admin.locked_until = None
    db.add(AuditLog(actor_user_id=None, action="admin_reset", target_type="user", target_id=str(admin.id),
                    details={"source": "env_reset"}))
    await db.commit()
    return True


async def seed_admin(db: AsyncSession) -> bool:
    s = get_settings()
    if not (s.admin_username and s.admin_password):
        return False
    count = await db.scalar(select(func.count()).select_from(User))
    if count:
        return False
    user = User(
        username=s.admin_username,
        full_name=s.admin_full_name,
        password_hash=hash_password(s.admin_password),
        role="admin",
        can_view_financials=True,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # Another server instance seeded the same admin a moment earlier (serverless cold starts).
        await db.rollback()
        return False
    db.add(AuditLog(actor_user_id=None, action="user_created", target_type="user", target_id=str(user.id),
                    details={"source": "env_seed"}))
    await db.commit()
    return True
