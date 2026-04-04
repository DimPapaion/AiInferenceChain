"""
ChainDB — SQLite persistence for InferenceChain.

Stores:
  blocks      — every committed block (header + serialised JSON)
  state_snap  — latest chain state snapshot (balances, stakes, nodes, etc.)

On startup:
  1. If db file exists → replay all blocks to rebuild in-memory Chain
  2. If not           → start fresh with genesis, persist immediately

SQLite is used because it is:
  - Built into Python (zero extra deps)
  - Transactional (no partial writes)
  - Fast enough for a research blockchain node
  - Single-file, easy to copy/backup

Schema
------
blocks (height INTEGER PK, hash TEXT, data TEXT)
  data = JSON from Block.to_dict()

state_snap (id INTEGER PK CHECK(id=1), data TEXT)
  data = JSON of the full ChainState

meta (key TEXT PK, value TEXT)
  Stores: genesis_hash, schema_version
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from core.blockchain.block import Block
from core.blockchain.chain import Chain, ChainState
from core.blockchain.genesis import create_genesis_block

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE IF NOT EXISTS blocks (
    height  INTEGER PRIMARY KEY,
    hash    TEXT    NOT NULL,
    data    TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS state_snap (
    id      INTEGER PRIMARY KEY CHECK(id = 1),
    data    TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key     TEXT    PRIMARY KEY,
    value   TEXT    NOT NULL
);
"""


class ChainDB:
    """
    SQLite-backed persistence for the InferenceChain ledger.
    Thread-safe via a single connection + WAL mode.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,   # autocommit; we manage transactions manually
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_DDL)
        self._ensure_meta()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _ensure_meta(self) -> None:
        cur = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES('schema_version',?)",
                (SCHEMA_VERSION,),
            )

    # ── Block persistence ─────────────────────────────────────────────────────

    def save_block(self, block: Block) -> None:
        """Persist a committed block. Idempotent (upsert)."""
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO blocks(height, hash, data) VALUES(?,?,?)",
                (block.height, block.hash, json.dumps(block.to_dict())),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def load_block(self, height: int) -> Optional[Block]:
        cur = self._conn.execute(
            "SELECT data FROM blocks WHERE height=?", (height,)
        )
        row = cur.fetchone()
        return Block.from_dict(json.loads(row[0])) if row else None

    def load_all_blocks(self) -> list[Block]:
        """Load all blocks in height order — used for chain replay on startup."""
        cur = self._conn.execute("SELECT data FROM blocks ORDER BY height ASC")
        blocks = []
        for (data,) in cur.fetchall():
            try:
                blocks.append(Block.from_dict(json.loads(data)))
            except Exception as e:
                log.error("Corrupted block in DB: %s", e)
        return blocks

    def block_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM blocks")
        return cur.fetchone()[0]

    # ── State snapshot ────────────────────────────────────────────────────────

    def save_state(self, state: ChainState) -> None:
        """Persist the full chain state (called after each committed block)."""
        data = json.dumps(_state_to_dict(state))
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO state_snap(id, data) VALUES(1,?)", (data,)
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def load_state(self) -> Optional[ChainState]:
        cur = self._conn.execute("SELECT data FROM state_snap WHERE id=1")
        row = cur.fetchone()
        return _state_from_dict(json.loads(row[0])) if row else None

    # ── Meta ──────────────────────────────────────────────────────────────────

    def get_meta(self, key: str) -> Optional[str]:
        cur = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value)
        )

    def close(self) -> None:
        self._conn.close()

    def __repr__(self) -> str:
        return f"ChainDB({self.db_path}, blocks={self.block_count()})"


# ── Chain state serialisation ─────────────────────────────────────────────────

def _state_to_dict(state: ChainState) -> dict:
    return {
        "balances":      state.balances,
        "stakes":        state.stakes,
        "nonces":        state.nonces,
        "reputations":   state.reputations,
        "nodes":         {k: v.to_dict() for k, v in state.nodes.items()},
        "contracts":     {k: v.to_dict() for k, v in state.contracts.items()},
        "inference_log": state.inference_log,
        "pom_states":    state.pom_states,
        "pubkeys":       state.pubkeys,
    }


def _state_from_dict(d: dict) -> ChainState:
    from core.blockchain.chain import NodeInfo, ContractInfo
    state = ChainState(
        balances      = d.get("balances", {}),
        stakes        = d.get("stakes", {}),
        nonces        = d.get("nonces", {}),
        reputations   = d.get("reputations", {}),
        inference_log = d.get("inference_log", {}),
        pom_states    = d.get("pom_states", {}),
        pubkeys       = d.get("pubkeys", {}),
    )
    for addr, nd in d.get("nodes", {}).items():
        state.nodes[addr] = NodeInfo(
            node_id       = nd["node_id"],
            address       = nd["address"],
            node_type     = nd["node_type"],
            public_key    = nd["public_key"],
            endpoint      = nd["endpoint"],
            registered_at = nd["registered_at"],
            is_active     = nd.get("is_active", False),
            pom_verified  = nd.get("pom_verified", False),
            pom_block     = nd.get("pom_block", -1),
            model_name    = nd.get("model_name", ""),
            weights_hash  = nd.get("weights_hash", ""),
            dataset_id    = nd.get("dataset_id", ""),
            architecture  = nd.get("architecture", {}),
        )
    for addr, cd in d.get("contracts", {}).items():
        from core.blockchain.chain import ContractInfo
        state.contracts[addr] = ContractInfo(
            address    = cd["address"],
            deployer   = cd["deployer"],
            bytecode   = cd["bytecode"],
            abi        = cd["abi"],
            state      = cd.get("state", {}),
            created_at = cd.get("created_at", 0),
        )
    return state


# ── Factory — open or create a persisted Chain ────────────────────────────────

def open_or_create_chain(
    db_path:             str | Path,
    initial_allocations: dict[str, float] | None = None,
    initial_nodes:       list[dict] | None = None,
    initial_dnn_nodes:   list[dict] | None = None,
    f:                   int = 1,
) -> tuple[Chain, ChainDB]:
    """
    Load an existing chain from disk, or create a fresh one with genesis.

    Returns (Chain, ChainDB) — the DB must be passed to the NodeService
    so blocks are persisted as they are appended.
    """
    db = ChainDB(db_path)

    if db.block_count() > 0:
        log.info("Loading chain from %s (%d blocks)…", db_path, db.block_count())
        blocks = db.load_all_blocks()
        genesis = blocks[0]
        chain   = Chain(genesis, f=f)
        for block in blocks[1:]:
            try:
                chain.append(block)
            except ValueError as e:
                log.error("Replay error at height %d: %s — stopping replay", block.height, e)
                break
        log.info("Chain loaded — height=%d tip=%s…", chain.height, chain.tip.hash[:12])
    else:
        log.info("No existing chain found at %s — creating genesis", db_path)
        genesis = create_genesis_block(
            initial_allocations = initial_allocations,
            initial_nodes       = initial_nodes,
            initial_dnn_nodes   = initial_dnn_nodes,
        )
        chain = Chain(genesis, f=f)
        db.save_block(genesis)
        db.save_state(chain.state)
        db.set_meta("genesis_hash", genesis.hash)
        log.info("Genesis block created — hash=%s…", genesis.hash[:12])

    return chain, db
