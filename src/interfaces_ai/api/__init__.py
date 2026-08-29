"""ASGI entry: `uvicorn interfaces_ai.api.app:app`."""

from interfaces_ai.api.app import app, create_app

__all__ = ["app", "create_app"]
