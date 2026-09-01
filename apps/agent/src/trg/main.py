"""TRG Agent Team — FastAPI application entry."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trg.agents.seeds import seed_if_empty
from trg.api.routes import router
from trg.config.settings import get_settings
from trg.orchestrator.agent_builder import AgentBuilder
from trg.orchestrator.manager import LifeCoordinator
from trg.orchestrator.registry import AgentRegistry


async def _bootstrap() -> None:
    """Ensure the seed agents exist on first boot."""
    settings = get_settings()
    registry = AgentRegistry(settings)
    seed_if_empty(registry)
    # Pre-create Qdrant collections for every registered agent
    coord = LifeCoordinator(settings, registry=registry)
    for agent in registry.list():
        await coord.retriever.ensure_collection(agent.qdrant_collection)
    await coord.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    registry = AgentRegistry(settings)
    seed_if_empty(registry)

    coordinator = LifeCoordinator(settings, registry=registry)
    agent_builder = AgentBuilder(settings, registry=registry, coordinator=coordinator)

    app.state.settings = settings
    app.state.registry = registry
    app.state.coordinator = coordinator
    app.state.agent_builder = agent_builder

    yield

    # Shutdown
    await coordinator.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TRG Agent Team",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # PWA dev server
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
