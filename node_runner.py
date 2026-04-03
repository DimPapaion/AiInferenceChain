"""
node_runner.py — InferenceChain node entry point.

Runs two servers concurrently in the same asyncio event loop:
  1. FastAPI / uvicorn  — REST API on --port       (default 8000)
  2. P2P WebSocket      — gossip     on --p2p-port  (default port+1000)

Usage:
    python node_runner.py
    python node_runner.py --port 8001 --host 0.0.0.0
    python node_runner.py --port 8000 --peer http://192.168.1.10:8000

Example — two nodes on localhost:
    # Terminal 1
    python node_runner.py --port 8000

    # Terminal 2 (connects to node 1 as bootstrap peer)
    python node_runner.py --port 8001 --peer http://127.0.0.1:8000

Then open http://localhost:8000/docs
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import uvicorn

from core.api import create_app
from core.api.node_service import create_node_service
from core.network.p2p_server import P2PServer
from core.node.identity import NodeIdentity

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("node_runner")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="InferenceChain node")
    p.add_argument("--host",     default="0.0.0.0",       help="Bind host (REST + P2P)")
    p.add_argument("--port",     type=int, default=8000,   help="REST API port")
    p.add_argument("--p2p-port", type=int, default=None,
                   help="P2P WebSocket port (default: --port + 1000)")
    p.add_argument(
        "--peer", nargs="*", default=[],
        metavar="URL",
        help="Bootstrap peer REST base URLs, e.g. http://1.2.3.4:8000",
    )
    p.add_argument(
        "--allocate", nargs="*", default=[],
        metavar="ADDRESS:AMOUNT",
        help="Genesis token allocations e.g. aabb...:100000",
    )
    p.add_argument("--no-dev",  action="store_true", help="Disable /dev/* routes")
    p.add_argument("--f",       type=int, default=1,   help="BFT fault tolerance (f)")
    p.add_argument("--node-id", default=None,          help="Override node_id (default: fresh key)")
    return p.parse_args()


async def run(args: argparse.Namespace) -> None:
    # ── Parse genesis allocations ─────────────────────────────────────────────
    allocations: dict[str, float] = {}
    for item in (args.allocate or []):
        try:
            addr, amount = item.rsplit(":", 1)
            allocations[addr] = float(amount)
        except ValueError:
            log.warning("Skipping invalid --allocate entry: %s", item)

    if not allocations:
        dev_id = NodeIdentity.generate()
        allocations[dev_id.address] = 10_000_000.0
        log.info("Dev genesis identity : %s", dev_id.address)
        log.info("  private key        : %s", dev_id.private_key_hex)

    # ── Node service (Chain + Mempool) ────────────────────────────────────────
    svc = create_node_service(initial_allocations=allocations, f=args.f)
    log.info(
        "Chain initialised — height=%d  tip=%s…",
        svc.chain.height, svc.chain.tip.hash[:16],
    )

    # ── Identifiers ───────────────────────────────────────────────────────────
    rest_port  = args.port
    p2p_port   = args.p2p_port if args.p2p_port else rest_port + 1000
    endpoint   = f"http://{args.host}:{rest_port}"
    node_id    = args.node_id or f"node-{rest_port}"

    # ── P2P server ────────────────────────────────────────────────────────────
    p2p = P2PServer(
        node_service = svc,
        node_id      = node_id,
        endpoint     = endpoint,
        p2p_port     = p2p_port,
        host         = args.host,
    )
    for peer_url in (args.peer or []):
        p2p.add_bootstrap(peer_url.rstrip("/"))
        svc.add_peer(peer_url.rstrip("/"))

    # Attach p2p reference to svc so HTTP routes can gossip too
    svc._p2p_server = p2p  # type: ignore[attr-defined]

    # ── FastAPI app ───────────────────────────────────────────────────────────
    app = create_app(
        node_service = svc,
        node_id      = node_id,
        endpoint     = endpoint,
        dev_mode     = not args.no_dev,
    )

    log.info("REST API  : http://%s:%d/docs", args.host, rest_port)
    log.info("P2P WS    : ws://%s:%d", args.host, p2p_port)
    if not args.no_dev:
        log.info("Dev mode  : POST http://%s:%d/dev/seal", args.host, rest_port)

    # ── Run both servers concurrently ─────────────────────────────────────────
    uvicorn_config = uvicorn.Config(
        app       = app,
        host      = args.host,
        port      = rest_port,
        log_level = "info",
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)

    await asyncio.gather(
        uvicorn_server.serve(),
        p2p.start(),
    )


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        log.info("Node stopped.")


if __name__ == "__main__":
    main()
