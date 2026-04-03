"""
node_runner.py — InferenceChain node entry point.

Runs three concurrent tasks in the same asyncio event loop:
  1. FastAPI / uvicorn  — REST API on --port        (default 8000)
  2. P2P WebSocket      — gossip    on --p2p-port   (default port+1000)
  3. ConsensusEngine    — block production loop

Storage:
  --db-path    SQLite database file (default: data/chain.db)
               Omit to run in-memory only (tests / ephemeral nodes).

Peer discovery:
  --peer URL   Bootstrap peers; added to data/peers.txt automatically.
               On restart, previously discovered peers are reloaded from
               the seed file without needing --peer again.

Image store:
  --image-dir  Directory for content-addressed image blobs
               (default: data/images).  DNN nodes store images here so
               QoI validators can retrieve them by hash.

Usage:
    python node_runner.py
    python node_runner.py --port 8001 --peer http://127.0.0.1:8000
    python node_runner.py --db-path data/chain.db --port 8000

Example — two persistent nodes on localhost:
    # Terminal 1
    python node_runner.py --port 8000 --db-path data/node1.db

    # Terminal 2
    python node_runner.py --port 8001 --db-path data/node2.db \\
        --peer http://127.0.0.1:8000

Then open http://localhost:8000/docs
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from core.api import create_app
from core.api.node_service import create_node_service, create_persistent_node_service
from core.consensus.engine import ConsensusEngine
from core.network.discovery import PeerDiscovery
from core.network.p2p_server import P2PServer
from core.node.identity import NodeIdentity
from core.serving.image_store import ImageStore

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("node_runner")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="InferenceChain node")
    p.add_argument("--host",      default="0.0.0.0",       help="Bind host (REST + P2P)")
    p.add_argument("--port",      type=int, default=8000,   help="REST API port")
    p.add_argument("--p2p-port",  type=int, default=None,
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
    p.add_argument("--no-dev",    action="store_true", help="Disable /dev/* routes")
    p.add_argument("--f",         type=int, default=1,   help="BFT fault tolerance (f)")
    p.add_argument("--node-id",   default=None,          help="Override node_id (default: fresh key)")
    p.add_argument("--db-path",   default=None,
                   help="SQLite DB path (e.g. data/chain.db).  Omit for in-memory mode.")
    p.add_argument("--seed-file", default="data/peers.txt",
                   help="Peer seed file path (default: data/peers.txt)")
    p.add_argument("--image-dir", default="data/images",
                   help="Content-addressed image store directory (default: data/images)")
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

    # ── Node service (Chain + Mempool + optional DB) ───────────────────────────
    if args.db_path:
        svc = create_persistent_node_service(
            db_path             = args.db_path,
            initial_allocations = allocations,
            f                   = args.f,
        )
        log.info("Persistent storage   : %s", args.db_path)
    else:
        svc = create_node_service(initial_allocations=allocations, f=args.f)
        log.info("Running in-memory (no --db-path)")

    log.info(
        "Chain initialised    : height=%d  tip=%s…",
        svc.chain.height, svc.chain.tip.hash[:16],
    )

    # ── Content-addressed image store ─────────────────────────────────────────
    image_store = ImageStore(base_dir=args.image_dir)
    log.info("Image store          : %s (%d images)", args.image_dir, image_store.count())

    # ── Peer discovery ────────────────────────────────────────────────────────
    discovery = PeerDiscovery(
        seed_file   = args.seed_file,
        extra_peers = list(args.peer or []),
    )
    log.info("Peer discovery       : %d known peers", len(discovery))

    # ── Identifiers ───────────────────────────────────────────────────────────
    rest_port = args.port
    p2p_port  = args.p2p_port if args.p2p_port else rest_port + 1000
    endpoint  = f"http://{args.host}:{rest_port}"
    node_id   = args.node_id or f"node-{rest_port}"

    # ── P2P server ────────────────────────────────────────────────────────────
    p2p = P2PServer(
        node_service = svc,
        node_id      = node_id,
        endpoint     = endpoint,
        p2p_port     = p2p_port,
        host         = args.host,
    )
    # Seed bootstrap peers from discovery (file + CLI --peer flags)
    p2p.attach_discovery(discovery)
    for peer_url in discovery.seed_peers():
        p2p.add_bootstrap(peer_url)
        svc.add_peer(peer_url)

    # Attach p2p reference to svc so HTTP routes can gossip too
    svc._p2p_server = p2p  # type: ignore[attr-defined]

    # ── Consensus engine ──────────────────────────────────────────────────────
    engine = ConsensusEngine(
        node_service = svc,
        node_id      = node_id,
        node_type    = "pos",   # "dnn" when model loading is wired
        f            = args.f,
    )
    engine.attach_p2p(p2p)
    engine.attach_image_store(image_store)
    p2p.attach_consensus(engine)

    # ── FastAPI app ───────────────────────────────────────────────────────────
    app = create_app(
        node_service = svc,
        node_id      = node_id,
        endpoint     = endpoint,
        dev_mode     = not args.no_dev,
        image_store  = image_store,
    )

    log.info("REST API             : http://localhost:%d/docs", rest_port)
    log.info("P2P WebSocket        : ws://%s:%d", args.host, p2p_port)
    if not args.no_dev:
        log.info("Dev mode             : POST http://localhost:%d/dev/seal", rest_port)

    # ── Run all three concurrently ────────────────────────────────────────────
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
        engine.run(),
    )


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        log.info("Node stopped.")


if __name__ == "__main__":
    main()
