"""
InferenceChain REST API — FastAPI application factory.

Usage:
    from core.api import create_app
    app = create_app(node_service, node_id="abc...", endpoint="http://0.0.0.0:8000")

Or run directly via node_runner.py.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.api.node_service import NodeService
from core.api.routes import chain, state, tx, inference, p2p, dev


def create_app(
    node_service: NodeService,
    node_id:      str  = "unknown",
    endpoint:     str  = "http://0.0.0.0:8000",
    dev_mode:     bool = True,
    cors_origins: list[str] | None = None,
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

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(chain.router)
    app.include_router(state.router)
    app.include_router(tx.router)
    app.include_router(inference.router)
    app.include_router(p2p.router)
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

    return app
