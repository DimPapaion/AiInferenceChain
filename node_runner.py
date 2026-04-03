"""
node_runner.py — InferenceChain node entry point.

Starts a single node with:
  - REST API (FastAPI / uvicorn) on --port (default 8000)
  - A genesis block with optional initial token allocations
  - Dev mode enabled by default (POST /dev/seal to produce blocks)

Usage:
    python node_runner.py
    python node_runner.py --port 8001 --host 0.0.0.0
    python node_runner.py --port 8000 --allocate <address>:<amount> ...

Example (two nodes on localhost):
    python node_runner.py --port 8000
    python node_runner.py --port 8001
    # Then POST /p2p/peers/add {"url": "http://127.0.0.1:8000"} on node 8001
"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from core.api import create_app
from core.api.node_service import create_node_service
from core.node.identity import NodeIdentity

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("node_runner")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="InferenceChain node")
    p.add_argument("--host",     default="0.0.0.0",     help="Bind host")
    p.add_argument("--port",     type=int, default=8000, help="REST API port")
    p.add_argument(
        "--allocate", nargs="*", default=[],
        metavar="ADDRESS:AMOUNT",
        help="Genesis token allocations, e.g. aabb...:100000",
    )
    p.add_argument("--no-dev",  action="store_true", help="Disable /dev/* routes")
    p.add_argument("--f",       type=int, default=1,   help="BFT fault tolerance parameter")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Parse genesis allocations ─────────────────────────────────────────────
    allocations: dict[str, float] = {}
    for item in args.allocate:
        try:
            addr, amount = item.rsplit(":", 1)
            allocations[addr] = float(amount)
        except ValueError:
            log.warning("Skipping invalid --allocate entry: %s", item)

    # If no allocations given, mint genesis supply to a fresh dev identity
    if not allocations:
        dev_id = NodeIdentity.generate()
        allocations[dev_id.address] = 10_000_000.0
        log.info("Dev genesis identity: %s", dev_id.address)
        log.info("  private key: %s", dev_id.private_key_hex)

    # ── Bootstrap node service ────────────────────────────────────────────────
    svc = create_node_service(
        initial_allocations = allocations,
        f                   = args.f,
    )
    log.info(
        "Chain initialised — height=%d  tip=%s",
        svc.chain.height,
        svc.chain.tip.hash[:16],
    )

    # ── This node's identity (announce to peers) ──────────────────────────────
    endpoint = f"http://{args.host}:{args.port}"

    # ── Build FastAPI app ─────────────────────────────────────────────────────
    app = create_app(
        node_service = svc,
        node_id      = "node-dev",
        endpoint     = endpoint,
        dev_mode     = not args.no_dev,
    )

    log.info("Starting InferenceChain node on %s", endpoint)
    log.info("API docs: %s/docs", endpoint)
    if not args.no_dev:
        log.info("Dev mode ON — POST %s/dev/seal to produce blocks", endpoint)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
