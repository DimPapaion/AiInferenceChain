"""
InferenceChain REST API — FastAPI application factory.

Usage:
    from core.api import create_app
    app = create_app(node_service, node_id="abc...", endpoint="http://0.0.0.0:8000")

Or run directly via node_runner.py.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.api.node_service import NodeService
from core.api.routes import chain, state, tx, inference, p2p, dev, dashboard, websocket


def create_app(
    node_service: NodeService,
    node_id:      str  = "unknown",
    endpoint:     str  = "http://0.0.0.0:8000",
    dev_mode:     bool = True,
    cors_origins: list[str] | None = None,
    image_store=None,
) -> FastAPI:
    """
    Build and return the FastAPI application.

    Args:
        node_service: the shared NodeService instance
        node_id:      this node's address (shown in /p2p/status)
        endpoint:     this node's public base URL (announced to peers)
        dev_mode:     if True, include /dev/* routes for manual block sealing
        cors_origins: list of allowed CORS origins (default: allow all)
    """
    app = FastAPI(
        title       = "InferenceChain Node API",
        description = "Decentralised DNN Inference Blockchain — REST interface",
        version     = "0.1.0",
        docs_url    = "/docs",
        redoc_url   = "/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = cors_origins or ["*"],
        allow_methods     = ["*"],
        allow_headers     = ["*"],
        allow_credentials = True,
    )

    # ── Shared state ──────────────────────────────────────────────────────────
    app.state.node_service = node_service
    app.state.node_id      = node_id
    app.state.endpoint     = endpoint
    app.state.image_store  = image_store

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(chain.router)
    app.include_router(state.router)
    app.include_router(tx.router)
    app.include_router(inference.router)
    app.include_router(p2p.router)
    app.include_router(dashboard.router)
    app.include_router(websocket.router)
    if dev_mode:
        app.include_router(dev.router)

    # ── Root ──────────────────────────────────────────────────────────────────
    @app.get("/", tags=["root"])
    async def root():
        return {
            "name":    "InferenceChain",
            "version": "0.1.0",
            "node_id": node_id,
            "docs":    "/docs",
        }

    # ── Frontend dashboard (served at /ui/) ───────────────────────────────────
    # Serve the compiled React build so the UI is accessible via /ui when running
    # behind a tunnel (ngrok) or any reverse proxy.
    frontend_build = Path(__file__).parent.parent.parent / "frontend" / "build"
    if frontend_build.is_dir():
        app.mount("/ui", StaticFiles(directory=str(frontend_build), html=True), name="ui")

    return app
