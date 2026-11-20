"""BRIHA API entrypoint: `uv run uvicorn app.main:app --reload`."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, text

from app.api import admin, auth, chat, conversations
from app.config import get_settings
from app.datasources.mock import MockDataSource
from app.db.models import Conversation, QueryRun, Session, utcnow
from app.db.seed import reset_admin, seed_admin, seed_glossary
from app.db.session import get_engine, sessionmaker
from app.errors import ApiError, api_error_handler
from app.llm.client import OpenAILLM
from app.pipeline.catalog import MasterCache
from app.pipeline.orchestrator import Orchestrator

log = structlog.get_logger()


def build_datasource(settings):
    if settings.datasource_mode == "mock":
        return MockDataSource(settings.today, settings.mock_faults)
    if settings.datasource_mode == "rest":
        from app.datasources.rest import RestDataSource

        return RestDataSource(settings)
    raise RuntimeError(f"Unsupported DATASOURCE_MODE={settings.datasource_mode!r} (use mock or rest)")


async def retention_job() -> None:
    s = get_settings()
    cutoff = utcnow() - timedelta(days=30 * s.retention_months)
    async with sessionmaker()() as db:
        await db.execute(delete(Session).where(Session.expires_at < utcnow() - timedelta(days=7)))
        await db.execute(delete(QueryRun).where(QueryRun.created_at < cutoff))
        await db.execute(delete(Conversation).where(Conversation.deleted_at.is_not(None),
                                                    Conversation.deleted_at < cutoff))
        await db.commit()
    log.info("retention_job_done")


ON_VERCEL = bool(os.environ.get("VERCEL"))


async def startup_tasks() -> None:
    """Seed glossary + first admin. On Vercel also create tables (no separate migration step there)."""
    settings = get_settings()
    if ON_VERCEL:
        from app.db.models import Base

        try:
            async with get_engine().begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:  # noqa: BLE001 - another instance may be creating them at the same moment
            log.warning("create_all_race")
    async with sessionmaker()() as db:
        await seed_glossary(db)
        if await seed_admin(db):
            log.info("admin_seeded", username=settings.admin_username)
        elif await reset_admin(db):
            log.warning("admin_reset", username=settings.admin_username)


def create_app(*, llm=None, datasource=None, run_startup: bool = True) -> FastAPI:
    settings = get_settings()
    startup_lock = asyncio.Lock()
    startup_done = {"ok": not run_startup}

    async def ensure_startup() -> None:
        if startup_done["ok"]:
            return
        async with startup_lock:
            if not startup_done["ok"]:
                await startup_tasks()
                startup_done["ok"] = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if run_startup:
            try:
                await ensure_startup()
            except Exception:
                log.exception("startup_failed_database_unreachable")
        if run_startup and not ON_VERCEL:  # serverless: no long-running scheduler
            scheduler = AsyncIOScheduler(timezone=settings.app_timezone)
            scheduler.add_job(retention_job, "cron", hour=3, minute=15)
            scheduler.start()
        log.info("briha_started", datasource=settings.datasource_mode, env=settings.app_env)
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="BRIHA API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if settings.app_env != "production" else None, openapi_url="/api/openapi.json")
    ds = datasource or build_datasource(settings)
    if llm is None and settings.llm_mode == "offline_demo":
        from app.llm.offline_demo import OfflineDemoLLM

        llm = OfflineDemoLLM()
        log.warning("llm_mode_offline_demo", note="keyword rules, NOT GPT-5; for testing only")
    if llm is None and settings.llm_mode == "gemini":
        from app.llm.client import GeminiLLM

        llm = GeminiLLM(settings)
    the_llm = llm or OpenAILLM(settings)
    app.state.datasource = ds
    app.state.llm = the_llm
    app.state.orchestrator = Orchestrator(the_llm, ds, settings, MasterCache(ds, settings.master_data_cache_hours))
    app.add_exception_handler(ApiError, api_error_handler)

    @app.middleware("http")
    async def startup_once(request: Request, call_next):
        # Some serverless platforms don't run the lifespan; make sure seeding happened before serving.
        try:
            await ensure_startup()
        except Exception:
            log.exception("startup_failed_database_unreachable")
            if request.url.path != "/api/health":
                return JSONResponse({"error": {"code": "DB_UNAVAILABLE", "message":
                                     "BRIHA's database is not connected yet. Please try again shortly."}},
                                    status_code=503)
        return await call_next(request)

    for r in (auth.router, conversations.router, chat.router, admin.router):
        app.include_router(r)

    @app.get("/api/health", tags=["health"])
    async def health(request: Request):
        db_ok = True
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            db_ok = False
        ds_ok = await request.app.state.datasource.health()
        llm = request.app.state.llm
        openai_ok = await llm.ping() if hasattr(llm, "ping") else True
        status = "ok" if db_ok and ds_ok and openai_ok else "degraded"
        return {"status": status, "db": db_ok, "datasource": ds_ok, "datasource_mode": settings.datasource_mode,
                "openai": openai_ok, "llm_mode": settings.llm_mode}

    return app


app = create_app()
