"""Entrypoint ASGI usado pela Vercel."""

from backend.app.main import app

__all__ = ["app"]
