"""
Chain — the main ledger for InferenceChain.

Manages:
  - Ordered list of committed blocks
  - Chain state (balances, stakes, nodes, inference log, contracts)
  - Block validation before appending
  - State transitions driven by transactions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .block import Block, BlockType
from .transaction import (
    Transaction, TxType, TxFamily,
    ConsensusResultPayload,
)
from .constants import (
    MIN_STAKE, INFERENCE_REWARD, SLASH_PENALTY,
    DEFAULT_F,
)
from .utils import compute_merkle_root


# ── State types ───────────────────────────────────────────────────────────────

@dataclass
class NodeInfo:
    """Metadata for a registered inference node."""
    node_id:       str
    address:       str
    model_name:    str
    public_key:    str
    endpoint:      str
    registered_at: int           # block height
    is_active:     bool = True

    def to_dict(self) -> dict:
        return {
            "node_id":       self.node_id,
            "address":       self.address,
            "model_name":    self.model_name,
            "public_key":    self.public_key,
            "endpoint":      self.endpoint,
            "registered_at": self.registered_at,
            "is_active":     self.is_active,
        }


@dataclass
class ContractInfo:
    """Deployed smart contract metadata."""
    address:    str
    deployer:   str
    bytecode:   str
    abi:        dict
    state:      dict = field(default_factory=dict)
    created_at: int  = 0

    def to_dict(self) -> dict:
        return {
            "address":    self.address,
            "deployer":   self.deployer,
            "bytecode":   self.bytecode,
            "abi":        self.abi,
            "state":      self.state,
            "created_at": self.created_at,
        }


@dataclass
class ChainState:
    """
    Full ledger state — what the chain currently looks like after all blocks.
    """
    balances:      dict[str, float]       = field(default_factory=dict)
    stakes:        dict[str, float]       = field(default_factory=dict)
    nonces:        dict[str, int]         = field(default_factory=dict)
    nodes:         dict[str, NodeInfo]    = field(default_factory=dict)
    contracts:     dict[str, ContractInfo]= field(default_factory=dict)
    inference_log: dict[str, dict]        = field(default_factory=dict)

    def balance_of(self, address: str) -> float:
        return self.balances.get(address, 0.0)

    def stake_of(self, address: str) -> float:
        return self.stakes.get(address, 0.0)

    def nonce_of(self, address: str) -> int:
        return self.nonces.get(address, 0)

    def active_nodes(self) -> list[NodeInfo]:
        return [n for n in self.nodes.values() if n.is_active]

    def validator_set(self) -> list[NodeInfo]:
        """Nodes eligible to participate in consensus (stake >= MIN_STAKE)."""
        return [n for n in self.active_nodes() if self.stake_of(n.address) >= MIN_STAKE]


# ── Chain ─────────────────────────────────────────────────────────────────────

class Chain:
    def __init__(self, genesis: Block, f: int = DEFAULT_F) -> None:
        self.f      = f
        self.blocks: list[Block] = []
        self.state  = ChainState()
        self._append_genesis(genesis)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def height(self) -> int:
        return len(self.blocks) - 1

    @property
    def tip(self) -> Block:
        return self.blocks[-1]

    # ── Public interface ──────────────────────────────────────────────────────

    def append(self, block: Block) -> None:
        """Validate and append a new block, updating chain state."""
        self._validate_block(block)
        self._apply_block(block)
        self.blocks.append(block)

    def get_block(self, height: int) -> Optional[Block]:
        if 0 <= height < len(self.blocks):
            return self.blocks[height]
        return None

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        for block in reversed(self.blocks):
            if block.hash == block_hash:
                return block
        return None

    def get_inference_result(self, request_id: str) -> Optional[dict]:
        return self.state.inference_log.get(request_id)

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_block(self, block: Block) -> None:
        tip = self.tip

        if block.header.prev_hash != tip.hash:
            raise ValueError(
                f"Invalid prev_hash: expected {tip.hash[:8]}, got {block.header.prev_hash[:8]}"
            )
        if block.header.height != tip.header.height + 1:
            raise ValueError(
                f"Invalid height: expected {tip.header.height + 1}, got {block.header.height}"
            )
        if not block.consensus_proof.is_valid(self.f):
            raise ValueError(
                f"Insufficient consensus signatures: "
                f"need {2 * self.f + 1}, got {len(block.consensus_proof.signatures)}"
            )
        if not block.verify_merkle_root():
            raise ValueError("Merkle root mismatch — block transactions may be tampered.")

        # Validate all simple txs, tracking intra-block nonce increments
        intra_nonces: dict[str, int] = {}
        for tx in block.simple_txs:
            self._validate_tx(tx, intra_nonces)
            intra_nonces[tx.sender] = tx.nonce

    def _validate_tx(self, tx: Transaction, intra_nonces: dict | None = None) -> None:
        """Validate a simple transaction against current state + intra-block nonces."""
        # Use intra-block nonce if sender already has a tx earlier in this block
        current_nonce = (
            intra_nonces[tx.sender]
            if intra_nonces and tx.sender in intra_nonces
            else self.state.nonce_of(tx.sender)
        )
        expected = current_nonce + 1
        if tx.nonce != expected:
            raise ValueError(
                f"Invalid nonce for {tx.sender[:8]}: expected {expected}, got {tx.nonce}"
            )

        balance = self.state.balance_of(tx.sender)
        fee     = tx.fee

        if tx.tx_type == TxType.TOKEN_TRANSFER:
            amount = tx.payload.amount
            if balance < amount + fee:
                raise ValueError(
                    f"Insufficient balance for transfer: has {balance}, needs {amount + fee}"
                )
        elif tx.tx_type == TxType.STAKE:
            amount = tx.payload.amount
            if balance < amount + fee:
                raise ValueError(
                    f"Insufficient balance for stake: has {balance}, needs {amount + fee}"
                )
        elif tx.tx_type == TxType.UNSTAKE:
            amount = tx.payload.amount
            staked = self.state.stake_of(tx.sender)
            if staked < amount:
                raise ValueError(
                    f"Insufficient stake to unstake: has {staked}, wants {amount}"
                )
            if balance < fee:
                raise ValueError("Insufficient balance to cover unstake fee")
        elif tx.tx_type in (TxType.CONTRACT_DEPLOY, TxType.CONTRACT_CALL, TxType.NODE_REGISTER):
            if balance < fee:
                raise ValueError("Insufficient balance to cover transaction fee")

    # ── State application ─────────────────────────────────────────────────────

    def _append_genesis(self, genesis: Block) -> None:
        """Apply genesis without validation (it has no predecessor)."""
        self._apply_block(genesis)
        self.blocks.append(genesis)

    def _apply_block(self, block: Block) -> None:
        proposer_id = block.header.proposer_id
        for tx in block.all_transactions:
            self._apply_tx(tx, block.height, proposer_id)

    def _apply_tx(self, tx: Transaction, height: int, proposer_id: str) -> None:
        # Distribute fee to the proposer for all simple txs
        if tx.family == TxFamily.SIMPLE and tx.fee > 0:
            self.state.balances[proposer_id] = (
                self.state.balance_of(proposer_id) + tx.fee
            )

        match tx.tx_type:

            case TxType.TOKEN_TRANSFER:
                amount = tx.payload.amount
                self.state.balances[tx.sender] = (
                    self.state.balance_of(tx.sender) - amount - tx.fee
                )
                self.state.balances[tx.recipient] = (
                    self.state.balance_of(tx.recipient) + amount
                )
                self.state.nonces[tx.sender] = tx.nonce

            case TxType.STAKE:
                amount = tx.payload.amount
                self.state.balances[tx.sender] = (
                    self.state.balance_of(tx.sender) - amount - tx.fee
                )
                self.state.stakes[tx.sender] = (
                    self.state.stake_of(tx.sender) + amount
                )
                self.state.nonces[tx.sender] = tx.nonce

            case TxType.UNSTAKE:
                amount = tx.payload.amount
                self.state.stakes[tx.sender] = (
                    self.state.stake_of(tx.sender) - amount
                )
                self.state.balances[tx.sender] = (
                    self.state.balance_of(tx.sender) + amount - tx.fee
                )
                self.state.nonces[tx.sender] = tx.nonce

            case TxType.NODE_REGISTER:
                p = tx.payload
                self.state.nodes[tx.sender] = NodeInfo(
                    node_id       = tx.sender,
                    address       = tx.sender,
                    model_name    = p.model_name,
                    public_key    = p.public_key,
                    endpoint      = p.endpoint,
                    registered_at = height,
                )
                self.state.balances[tx.sender] = (
                    self.state.balance_of(tx.sender) - tx.fee
                )
                self.state.nonces[tx.sender] = tx.nonce

            case TxType.CONTRACT_DEPLOY:
                from .utils import sha256_json
                p = tx.payload
                contract_address = sha256_json({
                    "deployer": tx.sender,
                    "nonce":    tx.nonce,
                })[:40]
                self.state.contracts[contract_address] = ContractInfo(
                    address    = contract_address,
                    deployer   = tx.sender,
                    bytecode   = p.bytecode,
                    abi        = p.abi,
                    created_at = height,
                )
                self.state.balances[tx.sender] = (
                    self.state.balance_of(tx.sender) - tx.fee
                )
                self.state.nonces[tx.sender] = tx.nonce

            case TxType.CONTRACT_CALL:
                # Execution delegated to the VM layer (called externally)
                self.state.balances[tx.sender] = (
                    self.state.balance_of(tx.sender) - tx.fee - tx.payload.value
                )
                self.state.nonces[tx.sender] = tx.nonce

            case TxType.REWARD:
                self.state.balances[tx.recipient] = (
                    self.state.balance_of(tx.recipient) + tx.payload.amount
                )

            case TxType.SLASH:
                current_stake = self.state.stake_of(tx.sender)
                self.state.stakes[tx.sender] = max(0.0, current_stake - tx.payload.amount)
                # Mark node inactive if stake drops below minimum
                if (
                    tx.sender in self.state.nodes
                    and self.state.stake_of(tx.sender) < MIN_STAKE
                ):
                    self.state.nodes[tx.sender].is_active = False

            case TxType.CONSENSUS_RESULT:
                p: ConsensusResultPayload = tx.payload
                self.state.inference_log[p.request_id] = p.to_dict()

            case TxType.INFERENCE_REQUEST | TxType.INFERENCE_RESPONSE:
                # These are recorded structurally in the block; no state change needed
                pass

    # ── Representation ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Chain(height={self.height}, "
            f"nodes={len(self.state.nodes)}, "
            f"tip={self.tip.hash[:8]}...)"
        )
