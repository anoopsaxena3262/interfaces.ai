from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interfaces_ai.agents.base import Store
from interfaces_ai.agents.discovery import DiscoveryAgent
from interfaces_ai.agents.escalation import EscalationAgent
from interfaces_ai.agents.replay import ReplayEngine
from interfaces_ai.api.routes import build_router
from interfaces_ai.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    store = Store()
    discovery = DiscoveryAgent(settings=settings)
    escalation = EscalationAgent(store=store, settings=settings)
    replay = ReplayEngine(escalation=escalation)

    app = FastAPI(
        title="interfaces.ai sandbox",
        version="0.1.0",
        description="Shared snapshot over three mock core extracts, plus discovery, replay, and hold-for-review.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = store
    app.state.discovery = discovery
    app.state.escalation = escalation
    app.state.replay = replay
    app.include_router(build_router())
    return app


app = create_app()
