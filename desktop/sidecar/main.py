"""
InferenceChain desktop sidecar — FastAPI server
Spawned by the Electron main process on app launch.
"""
import argparse
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.validate import router as validate_router
from routes.train import router as train_router
from routes.chain import router as chain_router

app = FastAPI(title="InferenceChain Sidecar", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "file://"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(validate_router, prefix="/validate")
app.include_router(train_router,    prefix="/train")
app.include_router(chain_router,    prefix="/chain")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=47291)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
