"""TRG Agent Team — FastAPI application entry."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

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

    await coordinator.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TRG Agent Team",
        version="0.1.0",
        lifespan=lifespan,
    )
    # In production (HF Space), the PWA and the API are on the same origin.
    # In local dev, the PWA runs on :3000 and the API on :8001 — allow CORS.
    pwa_dev_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    allowed_origins = ["*"]  # HF Space already same-origin; broad for dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,  # can't use credentials with "*"
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    # Serve the PWA static export (Next.js `output: export`).
    # Production: PWA_STATIC_DIR env var points to /app/web in the HF Space.
    # Dev: leave it alone (Next.js dev server runs separately on :3000).
    # main.py is at apps/agent/src/trg/main.py — parents[3] = apps/, parents[4] = repo root
    repo_root = Path(__file__).resolve().parents[4]
    pwa_dir = repo_root / "apps" / "web" / "out"
    pwa_dev_dir = repo_root / "apps" / "web" / "out"  # same path
    env_dir = None
    pwa_static_env = os.environ.get("PWA_STATIC_DIR")
    if pwa_static_env:
        env_dir = Path(pwa_static_env)

    candidates = []
    if env_dir and env_dir.exists():
        candidates.append(env_dir)
    if pwa_dir.exists():
        candidates.append(pwa_dir)

    for pwa in candidates:
        try:
            app.mount(
                "/_next",
                StaticFiles(directory=str(pwa / "_next"), check_dir=False),
                name="next-static",
            )

            @app.get("/", include_in_schema=False)
            async def _root() -> Response:
                return FileResponse(pwa / "index.html", media_type="text/html")

            @app.get("/setup", include_in_schema=False)
            async def _setup() -> Response:
                setup_html = pwa / "setup.html"
                if setup_html.exists():
                    return FileResponse(setup_html, media_type="text/html")
                return FileResponse(pwa / "index.html", media_type="text/html")

            @app.get("/manifest.json", include_in_schema=False)
            async def _manifest() -> Response:
                return FileResponse(pwa / "manifest.json", media_type="application/manifest+json")

            @app.get("/sw.js", include_in_schema=False)
            async def _sw() -> Response:
                return FileResponse(pwa / "sw.js", media_type="application/javascript")

            @app.get("/favicon.ico", include_in_schema=False)
            async def _favicon() -> Response:
                f = pwa / "favicon.ico"
                if f.exists():
                    return FileResponse(f, media_type="image/x-icon")
                return Response(status_code=204)

            print(f"[main] PWA mounted from {pwa}")
            break
        except Exception as e:
            print(f"[main] failed to mount PWA from {pwa}: {e}")

    return app


app = create_app()

