import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from training.trainer import run_training, is_active, cancel_run

router = APIRouter()

# In-memory store for the last started run config (single-run-at-a-time)
_pending: dict = {}


class TrainStartRequest(BaseModel):
    arch_source: str
    dataset_info: dict
    config: dict
    checkpoint_dir: str


@router.post("/start")
def train_start(req: TrainStartRequest):
    if is_active():
        return {"ok": False, "error": "A training run is already in progress."}
    global _pending
    _pending = req.model_dump()
    return {"ok": True}


@router.get("/stream")
async def train_stream():
    """
    SSE endpoint — streams epoch metrics as JSON lines.
    The client must have called /train/start first.
    """
    if not _pending:
        async def empty():
            yield "data: {\"type\":\"error\",\"error\":\"No training run configured. Call /train/start first.\"}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    async def event_gen():
        async for event in run_training(
            arch_source=_pending["arch_source"],
            dataset_info=_pending["dataset_info"],
            config=_pending["config"],
            checkpoint_dir=_pending["checkpoint_dir"],
        ):
            yield event

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/stop")
def train_stop():
    cancel_run()
    return {"ok": True}


@router.get("/status")
def train_status():
    return {"active": is_active()}
