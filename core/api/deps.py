"""
FastAPI dependency — injects the NodeService singleton into route handlers.

Usage in a route:
    from core.api.deps import get_service
    async def my_route(svc: NodeService = Depends(get_service)): ...

The singleton is stored on app.state.node_service, set during startup in
node_runner.py (or the app factory create_app()).
"""

from __future__ import annotations

from fastapi import Request
from core.api.node_service import NodeService


def get_service(request: Request) -> NodeService:
    return request.app.state.node_service
