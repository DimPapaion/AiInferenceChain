"""
Unit tests for core/consensus/ — block builder and consensus engine.

Engine tests drive the state machines directly without real asyncio tasks
or network sockets, using a fake NodeService with pre-seeded state.
"""

from __future__ import annotations

import asyncio
import pytest

from core.consensus import ConsensusEngine, build_pos_block, build_qoi_block
from core.api.node_service import create_node_service
from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.constants import NODE_TYPE_POS, NODE_TYPE_DNN
from core.blockchain.transaction import (
    Transaction, TxType,
    TokenTransferPayload, StakePayload, NodeRegisterPayload,
)
from core.blockchain.utils import compute_merkle_root, now
from core.node.identity import make_test_identity
from core.qoi.pos_consensus import PoSConsensusMachine, PoSOutcome, VoteMsg
from core.qoi.state_machine import QoIStateMachine

# ── Identities ────────────────────────────────────────────────────────────────

ID_A = make_test_identity(1)
ID_B = make_test_identity(2)
ID_C = make_test_identity(3)

ADDR_A = ID_A.address
ADDR_B = ID_B.address
ADDR_C = ID_C.address

GENESIS = {ADDR_A: 500_000.0, ADDR_B: 500_000.0, ADDR_C: 500_000.0}


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_svc():
    return create_node_service(initial_allocations=GENESIS, f=1)


def register_and_stake(svc, address: str, stake: float = 5_000.0):
    """
    Directly update chain state to simulate a registered + staked + active node.
    Bypasses tx validation — for test setup only.
    """
    from core.blockchain.chain import NodeInfo
    svc.chain.state.nodes[address] = NodeInfo(
        node_id       = address,
        address       = address,
        node_type     = NODE_TYPE_POS,
        public_key    = "aa" * 32,
        endpoint      = "http://127.0.0.1:8000",
        registered_at = 0,
        is_active     = True,
    )
    svc.chain.state.stakes[address]      = stake
    svc.chain.state.reputations[address] = 0.0


def make_pos_block(svc, proposer: str) -> Block:
    tip = svc.chain.tip
    merkle = compute_merkle_root([])
    header = BlockHeader(
        prev_hash=tip.hash, height=tip.height + 1, timestamp=now(),
        proposer_id=proposer, merkle_root=merkle,
        block_type=BlockType.POS, view=0,
    )
    proof = ConsensusProof(BlockType.POS, view=0)
    return Block(header=header, simple_txs=[], consensus_proof=proof)


def make_pos_outcome(svc, proposer: str) -> PoSOutcome:
    block = make_pos_block(svc, proposer)
    sms = {
        ADDR_A: PoSConsensusMachine(ADDR_A, proposer, f=1),
        ADDR_B: PoSConsensusMachine(ADDR_B, proposer, f=1),
        ADDR_C: PoSConsensusMachine(ADDR_C, proposer, f=1),
    }
    votes = [sms[proposer].propose_block(block)]
    for addr, sm in sms.items():
        if addr != proposer:
            v = sm.handle_proposed_block(block)
            if v:
                votes.append(v)
    for vote in votes:
        for sm in sms.values():
            sm.handle_vote(vote)
    return sms[proposer].outcome


# ═════════════════════════════════════════════════════════════════════════════
# BlockBuilder — PoS
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildPosBlock:
    def test_pos_block_correct_height(self):
        svc     = make_svc()
        register_and_stake(svc, ADDR_A)
        register_and_stake(svc, ADDR_B)
        register_and_stake(svc, ADDR_C)
        outcome = make_pos_outcome(svc, ADDR_A)
        assert outcome is not None
        block = build_pos_block(
            prev_hash  = svc.chain.tip.hash,
            height     = svc.chain.height + 1,
            simple_txs = [],
            outcome    = outcome,
        )
        assert block.height == 1
        assert block.header.block_type == BlockType.POS

    def test_pos_block_proof_has_signatures(self):
        svc     = make_svc()
        register_and_stake(svc, ADDR_A)
        register_and_stake(svc, ADDR_B)
        register_and_stake(svc, ADDR_C)
        outcome = make_pos_outcome(svc, ADDR_A)
        block   = build_pos_block(
            prev_hash=svc.chain.tip.hash, height=1, simple_txs=[], outcome=outcome
        )
        assert block.consensus_proof.is_valid(f=1)

    def test_pos_block_merkle_valid(self):
        svc = make_svc()
        register_and_stake(svc, ADDR_A)
        register_and_stake(svc, ADDR_B)
        register_and_stake(svc, ADDR_C)
        outcome = make_pos_outcome(svc, ADDR_A)
        block   = build_pos_block(
            prev_hash=svc.chain.tip.hash, height=1, simple_txs=[], outcome=outcome
        )
        assert block.verify_merkle_root()

    def test_pos_block_can_be_appended(self):
        svc     = make_svc()
        register_and_stake(svc, ADDR_A)
        register_and_stake(svc, ADDR_B)
        register_and_stake(svc, ADDR_C)
        outcome = make_pos_outcome(svc, ADDR_A)
        block   = build_pos_block(
            prev_hash=svc.chain.tip.hash, height=1, simple_txs=[], outcome=outcome
        )
        svc.chain.append(block)
        assert svc.chain.height == 1


# ═════════════════════════════════════════════════════════════════════════════
# BlockBuilder — QoI
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildQoIBlock:
    def _make_qoi_outcome(self):
        """Simulate a completed 4-node QoI round (reuse pattern from test_qoi.py)."""
        from core.qoi.messages import MsgType as QMT
        n, f = 4, 1
        primary = ADDR_A
        # Use hex addresses for nodes B, C, D
        node_ids = [ADDR_A, ADDR_B, ADDR_C, "d" * 40]
        probs = [0.05] * 10
        probs[3] = 0.55
        total = sum(probs)
        probs = [p / total for p in probs]

        sms = {nid: QoIStateMachine(nid, primary, f=f) for nid in node_ids}

        # Primary starts → PRE_PREPARE
        pre_prepare = sms[primary].start_round("req-1", "f" * 64, seq=1, own_probs=probs)
        assert pre_prepare is not None

        # Replicas start + handle PRE_PREPARE → PREPARE
        prepares = []
        for nid in node_ids:
            if nid == primary:
                continue
            sms[nid].start_round("req-1", "f" * 64, seq=1, own_probs=probs)
            prepare = sms[nid].handle_message(pre_prepare)
            if prepare:
                prepares.append(prepare)

        # Distribute PREPAREs → COMMIT
        commits = []
        for prepare in prepares:
            for nid in node_ids:
                result = sms[nid].handle_message(prepare)
                if result and result.msg_type == QMT.COMMIT and result not in commits:
                    commits.append(result)

        # Distribute COMMITs
        for commit in commits:
            for nid in node_ids:
                sms[nid].handle_message(commit)

        return sms[primary].outcome

    def test_qoi_block_type(self):
        svc     = make_svc()
        outcome = self._make_qoi_outcome()
        assert outcome is not None

        inference_tx = Transaction(
            tx_type=TxType.INFERENCE_REQUEST, sender=ADDR_A,
            payload=__import__("core.blockchain.transaction", fromlist=["InferenceRequestPayload"])
                    .InferenceRequestPayload(request_id="req-1", image_hash="f"*64, model_hint="any"),
            nonce=1, fee=1.0,
        )
        block = build_qoi_block(
            prev_hash    = svc.chain.tip.hash,
            height       = 1,
            proposer_id  = ADDR_A,
            inference_tx = inference_tx,
            simple_txs   = [],
            outcome      = outcome,
            block_fees   = 0.0,
        )
        assert block.header.block_type == BlockType.QOI
        assert block.inference_tx is not None
        assert block.verify_merkle_root()

    def test_qoi_block_has_system_txs(self):
        svc     = make_svc()
        outcome = self._make_qoi_outcome()
        from core.blockchain.transaction import InferenceRequestPayload
        inference_tx = Transaction(
            tx_type=TxType.INFERENCE_REQUEST, sender=ADDR_A,
            payload=InferenceRequestPayload(request_id="req-1", image_hash="f"*64, model_hint="any"),
            nonce=1, fee=1.0,
        )
        block = build_qoi_block(
            prev_hash=svc.chain.tip.hash, height=1, proposer_id=ADDR_A,
            inference_tx=inference_tx, simple_txs=[], outcome=outcome, block_fees=0.0,
        )
        system_types = {tx.tx_type for tx in block.system_txs}
        assert TxType.CONSENSUS_RESULT in system_types
        assert TxType.REWARD in system_types


# ═════════════════════════════════════════════════════════════════════════════
# ConsensusEngine — state + async dispatch
# ═════════════════════════════════════════════════════════════════════════════

class TestConsensusEngine:
    def _make_engine(self, node_id=ADDR_A):
        svc = make_svc()
        register_and_stake(svc, ADDR_A)
        register_and_stake(svc, ADDR_B)
        register_and_stake(svc, ADDR_C)
        engine = ConsensusEngine(svc, node_id=node_id, node_type="pos", f=1)
        return engine, svc

    def test_engine_initialises(self):
        engine, _ = self._make_engine()
        assert engine._running is False
        assert engine._pos_sm is None
        assert engine._qoi_sm is None

    def test_attach_p2p(self):
        engine, _ = self._make_engine()
        engine.attach_p2p("fake_p2p")
        assert engine._p2p == "fake_p2p"

    def test_handle_pos_vote_without_sm_does_nothing(self):
        engine, _ = self._make_engine()
        vote = {"node_id": ADDR_B, "block_hash": "a" * 64, "view": 0}
        asyncio.run(
            engine.handle_consensus_msg("POS_VOTE", vote)
        )
        # No crash, no state change

    def test_handle_pos_block_initialises_sm_and_votes(self):
        engine, svc = self._make_engine(ADDR_B)   # B is not the proposer

        # Initialise engine's PoS SM as a replica
        engine._pos_sm = PoSConsensusMachine(ADDR_B, ADDR_A, f=1)

        # Build a valid candidate block
        block = make_pos_block(svc, ADDR_A)
        asyncio.run(
            engine.handle_consensus_msg("POS_BLOCK", block.to_dict())
        )
        # After receiving the block, B's SM should have voted
        assert ADDR_B in engine._pos_sm._votes

    def test_pos_round_commits_single_node(self):
        """
        Single-node network (only A active with f=0).
        The proposer's own vote should immediately reach 2f+1=1.
        """
        svc = create_node_service(initial_allocations={ADDR_A: 500_000.0}, f=0)
        register_and_stake(svc, ADDR_A)
        engine = ConsensusEngine(svc, node_id=ADDR_A, node_type="pos", f=0)

        asyncio.run(engine._run_pos_round())

        assert svc.chain.height == 1

    def test_qoi_msg_routing_without_sm_ignored(self):
        engine, _ = self._make_engine()
        # Should not crash even with no active QoI SM
        asyncio.run(
            engine.handle_consensus_msg("QOI_MSG", {
                "msg_type": "prepare", "view": 0, "seq": 0,
                "sender_id": ADDR_B, "timestamp": now(),
                "request_id": "r", "probabilities": [0.1]*10, "predicted_class": 0,
            })
        )
