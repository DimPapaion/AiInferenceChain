"""
WebSocket routes for real-time dashboard updates.

Endpoints:
- /ws/consensus-rounds - Real-time consensus updates
- /ws/validators - Validator activity stream  
- /ws/models - Model validation stream
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.qoi.consensus_stream import get_stream_manager
from core.utils.logger import get_logger

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = get_logger("websocket_routes")


@router.websocket("/consensus-rounds")
async def consensus_rounds_stream(websocket: WebSocket):
    """
    WebSocket stream for consensus round updates.
    
    Emits events:
    - consensus_round: Round number, phase, status, participants
    """
    manager = get_stream_manager()
    await manager.connect(websocket, "consensus_rounds")
    
    try:
        logger.info("Client connected to consensus_rounds stream")
        # Keep connection alive, waiting for messages from broadcast
        while True:
            # This will raise WebSocketDisconnect when client disconnects
            await websocket.receive()
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, "consensus_rounds")
        logger.info("Client disconnected from consensus_rounds stream")


@router.websocket("/validators")
async def validators_stream(websocket: WebSocket):
    """
    WebSocket stream for validator activity updates.
    
    Emits events:
    - validator_activity: Action, details
    - validator_stats: Updated statistics
    """
    manager = get_stream_manager()
    await manager.connect(websocket, "validators")
    
    try:
        logger.info("Client connected to validators stream")
        while True:
            await websocket.receive()
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, "validators")
        logger.info("Client disconnected from validators stream")


@router.websocket("/models")
async def models_stream(websocket: WebSocket):
    """
    WebSocket stream for model validation updates.
    
    Emits events:
    - model_validation: Status, progress, message
    """
    manager = get_stream_manager()
    await manager.connect(websocket, "models")
    
    try:
        logger.info("Client connected to models stream")
        while True:
            await websocket.receive()
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, "models")
        logger.info("Client disconnected from models stream")
