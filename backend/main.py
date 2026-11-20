"""Entrypoint for Vercel (and any ASGI server): exposes the FastAPI app."""

from app.main import app

__all__ = ["app"]
