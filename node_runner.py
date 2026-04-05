# -*- coding: utf-8 -*-
"""
node_runner.py - InferenceChain node entry point.

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
from typing import Any

import uvicorn

from core.api import create_app
from core.api.node_service import create_node_service, create_persistent_node_service
from core.consensus.engine import ConsensusEngine
from core.llm import InferenceOrchestrator
from core.llm.provider import MockProvider, OllamaProvider, OpenAIProvider
from core.network.discovery import PeerDiscovery
from core.network.p2p_server import P2PServer
from core.node.identity import NodeIdentity
from core.node.inference_node import ModelHandle
from core.qoi.consensus_stream import get_stream_manager
from core.serving.image_store import ImageStore

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("node_runner")


def _load_config(path: str) -> dict[str, Any]:
    """Load a YAML testnet config file. Returns {} if path is None."""
    if not path:
        return {}
    try:
        import yaml  # pyyaml
    except ImportError:
        log.warning("pyyaml not installed — ignoring --config.  pip install pyyaml")
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="InferenceChain node")
    p.add_argument("--config",    default=None,
                   help="YAML config file (e.g. config/testnet.yaml).  "
                        "CLI flags override config file values.")
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
    p.add_argument("--db-path",   default="data/chain.db",
                   help="SQLite DB path (default: data/chain.db).  Pass empty string for in-memory mode.")
    p.add_argument("--seed-file", default="data/peers.txt",
                   help="Peer seed file path (default: data/peers.txt)")
    p.add_argument("--image-dir", default="data/images",
                   help="Content-addressed image store directory (default: data/images)")
    # ── DNN node options ──────────────────────────────────────────────────────
    p.add_argument("--node-type",   default="pos", choices=["pos", "dnn"],
                   help="Node role: 'pos' (default) or 'dnn' (runs inference + QoI consensus)")
    p.add_argument("--model",       default=None,
                   help="Model name for DNN nodes (e.g. resnet20, vgg11_bn).  "
                        "Required when --node-type dnn.")
    p.add_argument("--weights-dir", default="models/weights",
                   help="Directory containing .pth weight files (default: models/weights)")
    p.add_argument("--private-key", default=None,
                   help="Hex private key for this node's identity.  "
                        "Used for signing txs (DNN nodes).  Generates fresh key if omitted.")
    # ── LLM orchestration options ─────────────────────────────────────────────
    p.add_argument("--llm-provider", default=None,
                   choices=["openai", "ollama", "mock"],
                   help="LLM provider for the orchestration layer.  "
                        "'openai' requires OPENAI_API_KEY env var.  "
                        "'ollama' uses a local Ollama server (see --ollama-host).  "
                        "'mock' is deterministic and requires no network (tests/dev).  "
                        "Omit to disable /llm/* endpoints (503 on every call).")
    p.add_argument("--llm-model", default=None,
                   help="Model name for the LLM provider (default: gpt-4o-mini for openai, "
                        "llama3.2 for ollama).")
    p.add_argument("--ollama-host", default="http://localhost:11434",
                   help="Ollama server base URL (default: http://localhost:11434)")
    p.add_argument("--openai-key", default=None,
                   help="OpenAI API key (overrides OPENAI_API_KEY env var).")
    return p.parse_args()


async def run(args: argparse.Namespace) -> None:
    # ── Load config file (testnet.yaml etc.) ──────────────────────────────────
    cfg = _load_config(args.config)
    if cfg:
        log.info("Config loaded        : %s  (network=%s)", args.config, cfg.get("network", "?"))

    # ── Resolve effective values (CLI overrides config) ───────────────────────
    effective_f = args.f if args.f != 1 or not cfg.get("f") else cfg["f"]

    # ── Parse genesis allocations ─────────────────────────────────────────────
    allocations: dict[str, float] = {}

    # From config file first
    for addr, amount in (cfg.get("genesis_allocations") or {}).items():
        allocations[str(addr)] = float(amount)

    # CLI --allocate flags override/extend config allocations
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

    # ── Bootstrap peers: config + CLI ─────────────────────────────────────────
    config_peers: list[str] = [
        p.rstrip("/") for p in (cfg.get("bootstrap_peers") or [])
    ]
    cli_peers: list[str] = [p.rstrip("/") for p in (args.peer or [])]
    all_bootstrap_peers = list(dict.fromkeys(config_peers + cli_peers))  # dedup, order preserved

    # ── DNN nodes from config (pre-admitted in genesis) ───────────────────────
    initial_dnn_nodes: list[dict] | None = cfg.get("dnn_nodes") or None
    if initial_dnn_nodes:
        log.info("DNN genesis nodes    : %d pre-admitted", len(initial_dnn_nodes))

    # ── Node service (Chain + Mempool + optional DB) ───────────────────────────
    if args.db_path and args.db_path.strip():
        svc = create_persistent_node_service(
            db_path             = args.db_path,
            initial_allocations = allocations,
            initial_dnn_nodes   = initial_dnn_nodes,
            f                   = effective_f,
        )
        log.info("Persistent storage   : %s", args.db_path)
    else:
        svc = create_node_service(
            initial_allocations = allocations,
            initial_dnn_nodes   = initial_dnn_nodes,
            f                   = effective_f,
        )
        log.info("Running in-memory (--db-path='')")

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
    rest_port      = args.port
    p2p_port       = args.p2p_port if args.p2p_port else rest_port + 1000
    # Announce 127.0.0.1 when binding to 0.0.0.0 so peers on the same
    # machine can actually reach us. Override with --node-id / explicit host.
    announced_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    endpoint       = f"http://{announced_host}:{rest_port}"

    # For DNN nodes use a stable identity derived from the private key so the
    # address matches what is pre-admitted in the genesis block.
    if args.private_key:
        _identity = NodeIdentity.from_private_key(args.private_key)
        node_id   = _identity.address
        log.info("Node identity        : %s  (from --private-key)", node_id)
    else:
        node_id = args.node_id or f"node-{rest_port}"

    # ── P2P server ────────────────────────────────────────────────────────────
    p2p = P2PServer(
        node_service = svc,
        node_id      = node_id,
        endpoint     = endpoint,
        p2p_port     = p2p_port,
        host         = args.host,
    )
    # Seed bootstrap peers from discovery (file + CLI --peer flags + config)
    p2p.attach_discovery(discovery)
    for peer_url in discovery.seed_peers():
        p2p.add_bootstrap(peer_url)
        svc.add_peer(peer_url)
    # Also add config-file peers that weren't yet in the seed file
    for peer_url in all_bootstrap_peers:
        if peer_url not in discovery.all_peers():
            discovery.add(peer_url)
            p2p.add_bootstrap(peer_url)
            svc.add_peer(peer_url)

    # Attach p2p reference to svc so HTTP routes can gossip too
    svc._p2p_server = p2p  # type: ignore[attr-defined]

    # Wire image store into P2P so nodes can serve/fetch images from peers
    p2p.attach_image_store(image_store)

    # ── DNN model loading (DNN nodes only) ───────────────────────────────────
    model_handle: ModelHandle | None = None
    node_type = args.node_type

    if node_type == "dnn":
        if not args.model:
            log.error("--model is required when --node-type dnn")
            return
        import hashlib, os as _os
        weights_path = _os.path.join(args.weights_dir, f"{args.model}.pth")
        if not _os.path.exists(weights_path):
            log.error("Weights not found: %s  (run scratch/train_cifar10_models.py)", weights_path)
            return
        # Compute weights hash for on-chain registration
        _h = hashlib.sha256()
        with open(weights_path, "rb") as _f:
            for _chunk in iter(lambda: _f.read(8192), b""):
                _h.update(_chunk)
        weights_hash = _h.hexdigest()
        model_handle = ModelHandle(
            name         = args.model,
            architecture = {},       # filled by ModelRegistry at load time
            weights_path = weights_path,
            weights_hash = weights_hash,
            dataset_id   = "cifar10",
        )
        model_handle.load()
        log.info("DNN model loaded     : %s  hash=%s…", args.model, weights_hash[:16])

    # ── Consensus engine ──────────────────────────────────────────────────────
    engine = ConsensusEngine(
        node_service = svc,
        node_id      = node_id,
        node_type    = node_type,
        model        = model_handle,
        f            = effective_f,
    )
    engine.attach_p2p(p2p)
    engine.attach_image_store(image_store)
    p2p.attach_consensus(engine)

    # ── Wire WebSocket stream to consensus events ─────────────────────────────
    get_stream_manager().wire_to_event_bus()

    # ── LLM orchestrator (optional) ────────────────────────────────────────────
    orchestrator = None
    if args.llm_provider:
        if args.llm_provider == "openai":
            import os
            api_key  = args.openai_key or os.environ.get("OPENAI_API_KEY", "")
            model    = args.llm_model or "gpt-4o-mini"
            provider = OpenAIProvider(model=model, api_key=api_key)
            log.info("LLM provider         : OpenAI  model=%s", model)
        elif args.llm_provider == "ollama":
            model    = args.llm_model or "llama3.2"
            provider = OllamaProvider(model=model, host=args.ollama_host)
            log.info("LLM provider         : Ollama  host=%s  model=%s", args.ollama_host, model)
        else:  # mock
            provider = MockProvider()
            log.info("LLM provider         : Mock (deterministic)")
        orchestrator = InferenceOrchestrator(provider=provider)
    else:
        log.info("LLM provider         : disabled (omit --llm-provider to keep disabled)")

    # ── FastAPI app ────────────────────────────────────────────────────────
    app = create_app(
        node_service = svc,
        node_id      = node_id,
        endpoint     = endpoint,
        dev_mode     = not args.no_dev,
        image_store  = image_store,
        orchestrator = orchestrator,
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
