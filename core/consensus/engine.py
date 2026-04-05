"""
ConsensusEngine — the main autonomous block-production loop.

This is the heart of the InferenceChain node. It runs as a background
asyncio task alongside the FastAPI server and P2P gossip layer.

Two round types, driven by what is in the mempool:

  ── PoS round (default) ──────────────────────────────────────────────────
  1. Select proposer (stake × reputation weighted, deterministic)
  2. If we are the proposer:
       a. Pull simple txs from mempool
       b. Build a candidate PoS block
       c. Start PoSConsensusMachine, cast our own vote
       d. Broadcast candidate block via P2P (CONSENSUS message)
  3. On receiving a vote (from P2P / REST):
       a. Feed into PoSConsensusMachine
       b. If 2f+1 votes → call _commit_pos_block()
  4. Timeout → view change, new proposer

  ── QoI round (when inference request is pending) ────────────────────────
  1. Pop inference request from mempool
  2. Select proposer for this round
  3. If we are the primary:
       a. Run inference on the image (InferenceNode.model.predict)
       b. Start QoIStateMachine, generate PRE_PREPARE
       c. Broadcast PRE_PREPARE via P2P
  4. Feed incoming PREPARE / COMMIT / VIEW_CHANGE messages into QoIStateMachine
  5. If COMMITTED → call _commit_qoi_block()

Message routing:
  Incoming consensus messages (from P2P) → engine.handle_consensus_msg()
  Outgoing consensus messages → engine._broadcast_consensus()

The engine is node-type aware:
  - InferenceNode: participates in both QoI and PoS rounds
  - PoSNode: participates in PoS rounds only

Single-node / dev mode:
  When there is only one active node, it auto-commits (f=0 threshold met
  with just the proposer's own vote/prepare/commit).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Union

from core.api.node_service import NodeService
from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.constants import (
    DEFAULT_F, BLOCK_TIME_TARGET, MAX_SIMPLE_TXS,
    VIEW_CHANGE_TIMEOUT,
)
from core.blockchain.transaction import Transaction, TxType
from core.blockchain.utils import compute_merkle_root, now
from core.consensus.block_builder import build_pos_block, build_qoi_block
from core.consensus.quorum import select_quorum, Quorum
from core.qoi.messages import (
    MsgType as QoIMsgType, BaseMessage, PrePrepareMsg,
    PrepareMsg, CommitMsg, ViewChangeMsg, NewViewMsg,
    message_from_dict,
)
from core.events import EventType, get_global_bus
from core.qoi.pos_consensus import PoSConsensusMachine, PoSOutcome, VoteMsg
from core.qoi.proposer import select_proposer
from core.qoi.state_machine import QoIStateMachine, QoIPhase, ConsensusOutcome

log = logging.getLogger(__name__)


class ConsensusEngine:
    """
    Drives block production for a single InferenceChain node.
    One instance per node process; runs as a long-lived asyncio task.
    """

    def __init__(
        self,
        node_service: NodeService,
        node_id:      str,
        node_type:    str = "pos",   # "dnn" | "pos"
        model=None,                  # ModelHandle (DNN nodes only)
        f:            int = DEFAULT_F,
    ) -> None:
        self.svc       = node_service
        self.node_id   = node_id
        self.node_type = node_type
        self.model     = model
        self.f         = f

        # Active round state
        self._pos_sm:       Optional[PoSConsensusMachine] = None
        self._qoi_sm:       Optional[QoIStateMachine]     = None
        self._current_view: int   = 0
        self._round_seq:    int   = 0
        self._round_start:  float = 0.0

        # Pending PoS block candidate (set by proposer, awaiting votes)
        self._pending_pos_block: Optional[Block] = None

        # Pending inference tx for current QoI round
        self._pending_inference_tx: Optional[Transaction] = None

        # Elected S-BFT quorum for the current QoI round
        self._active_quorum: Optional[Quorum] = None

        self._running = False
        self._p2p: Optional[object] = None   # P2PServer, set via attach_p2p()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def attach_p2p(self, p2p_server) -> None:
        """Wire the P2P server so we can gossip consensus messages."""
        self._p2p = p2p_server

    async def run(self) -> None:
        """
        Main consensus loop.  Runs forever until cancelled.
        """
        self._running = True
        log.info("ConsensusEngine started — node_id=%s type=%s f=%d",
                 self.node_id[:8], self.node_type, self.f)
        try:
            while self._running:
                await self._run_round()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            log.info("ConsensusEngine stopped")

    async def stop(self) -> None:
        self._running = False

    # ── Round dispatcher ──────────────────────────────────────────────────────

    async def _run_round(self) -> None:
        """
        Decide whether to run a QoI round or a PoS round, then run it.

        Dispatch rules:
          1. Inference tx in mempool AND DNN validators are registered/active:
               → DNN nodes  : run QoI round
               → PoS nodes  : stand by (sleep one slot) so they don't produce
                              a competing PoS block at the same height.
                              The QoI block will arrive via P2P and be ingested.
          2. No inference tx (or no DNN validators available):
               → ALL nodes run a PoS round.
        """
        inference_tx       = self.svc.mempool.peek_inference()
        dnn_validators_up  = len(self.svc.chain.state.dnn_validators()) > 0

        if inference_tx is not None and dnn_validators_up:
            if self.node_type == "dnn" and self.model is not None:
                await self._run_qoi_round(inference_tx)
            else:
                # PoS node: wait one block slot while DNN committee completes QoI.
                # The committed QoI block arrives via P2P → ingest_block().
                await asyncio.sleep(BLOCK_TIME_TARGET)
        else:
            await self._run_pos_round()

    # ══════════════════════════════════════════════════════════════════════════
    # PoS Round
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_pos_round(self) -> None:
        """One full PoS consensus round (propose → vote → commit | timeout)."""
        chain   = self.svc.chain
        state   = chain.state
        tip     = chain.tip

        # ── Select proposer ───────────────────────────────────────────────────
        validators = state.pos_validators()
        if not validators:
            # No active validators yet — wait and retry
            await asyncio.sleep(BLOCK_TIME_TARGET)
            return

        proposer_id = select_proposer(
            nodes           = validators,
            stakes          = dict(state.stakes),
            reputations     = dict(state.reputations),
            prev_block_hash = tip.hash,
            view            = self._current_view,
        )
        if proposer_id is None:
            await asyncio.sleep(BLOCK_TIME_TARGET)
            return

        log.debug("PoS round view=%d proposer=%s…", self._current_view, proposer_id[:8])

        # Initialise per-node state machine
        self._pos_sm = PoSConsensusMachine(
            node_id     = self.node_id,
            proposer_id = proposer_id,
            f           = self.f,
        )
        self._round_start = now()

        # ── Proposer path ─────────────────────────────────────────────────────
        if self.node_id == proposer_id:
            block, vote = self._build_and_propose_pos_block(tip, state)
            self._pending_pos_block = block
            # Broadcast the candidate block + our vote to peers
            await self._broadcast_consensus("POS_BLOCK", block.to_dict())
            await self._broadcast_consensus("POS_VOTE",  vote.to_dict())

        # ── Wait for votes / timeout ──────────────────────────────────────────
        committed = await self._wait_for_pos_commit()
        if committed:
            self._current_view = 0   # reset view on success
        else:
            # Timeout — bump view (new proposer next round)
            self._current_view += 1
            log.info("PoS timeout view=%d — moving to view %d",
                     self._current_view - 1, self._current_view)

        # Cool-down between blocks
        elapsed = now() - self._round_start
        sleep_for = max(0.0, BLOCK_TIME_TARGET - elapsed)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

    def _build_and_propose_pos_block(self, tip, state) -> tuple[Block, VoteMsg]:
        """Build a candidate PoS block and cast the proposer's own vote."""
        nonces    = {a: state.nonce_of(a) for a in state.nonces}
        simple_txs = self.svc.mempool.select_simple(nonces, MAX_SIMPLE_TXS)
        merkle    = compute_merkle_root(simple_txs)

        header = BlockHeader(
            prev_hash   = tip.hash,
            height      = tip.height + 1,
            timestamp   = now(),
            proposer_id = self.node_id,
            merkle_root = merkle,
            block_type  = BlockType.POS,
            view        = self._current_view,
        )
        # Temporary proof — will be replaced with real sigs when we commit
        proof = ConsensusProof(BlockType.POS, view=self._current_view)
        block = Block(header=header, simple_txs=simple_txs, consensus_proof=proof)

        vote = self._pos_sm.propose_block(block)
        return block, vote

    async def _wait_for_pos_commit(self) -> bool:
        """
        Poll until either:
          - 2f+1 votes collected (committed=True), or
          - Timeout exceeded (committed=False)
        Returns True on commit, False on timeout.
        """
        deadline = now() + VIEW_CHANGE_TIMEOUT
        while now() < deadline:
            if self._pos_sm and self._pos_sm.outcome is not None:
                await self._commit_pos_block(self._pos_sm.outcome)
                return True
            await asyncio.sleep(0.05)
        return False

    async def _commit_pos_block(self, outcome: PoSOutcome) -> None:
        """Seal the PoS block into the chain and clean up mempool."""
        block = build_pos_block(
            prev_hash  = self.svc.chain.tip.hash,
            height     = self.svc.chain.height + 1,
            simple_txs = self._pending_pos_block.simple_txs
                         if self._pending_pos_block else [],
            outcome    = outcome,
        )
        result = await self.svc.ingest_block(block)
        if result["accepted"]:
            log.info(
                "PoS block committed height=%d txs=%d hash=%s…",
                block.height, block.tx_count, block.hash[:12],
            )
            get_global_bus().publish(
                EventType.POS_COMMITTED,
                data={
                    "height":   block.height,
                    "proposer": outcome.proposer_id,
                    "tx_count": block.tx_count,
                    "hash":     block.hash,
                },
            )
            # Gossip to peers
            if self._p2p:
                await self._p2p.broadcast_block(block.to_dict())
        else:
            log.warning("PoS block rejected: %s", result["reason"])

        self._pending_pos_block = None
        self._pos_sm = None

    # ══════════════════════════════════════════════════════════════════════════
    # QoI Round
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_qoi_round(self, inference_tx: Transaction) -> None:
        """
        One full S-BFT QoI consensus round (PRE_PREPARE → PREPARE → COMMIT).

        S-BFT layer:
          1. Elect a quorum of K nodes from eligible DNN validators, filtered
             by model/dataset. Quorum is deterministic: any node can verify it.
          2. If this node is NOT in the elected quorum — stand by for one slot.
             The committed QoI block will arrive via P2P.
          3. If this node IS in the quorum — run inference and participate in
             the PBFT-style QoI round using quorum-local f (not the global f).
        """
        chain = self.svc.chain
        state = chain.state
        tip   = chain.tip

        dnn_nodes = state.dnn_validators()
        if not dnn_nodes:
            await asyncio.sleep(BLOCK_TIME_TARGET)
            return

        # ── S-BFT: elect quorum for this request ─────────────────────────────
        request_id = inference_tx.payload.request_id
        image_hash = inference_tx.payload.image_hash
        model_hint = inference_tx.payload.model_hint   # "any" or specific model name
        dataset_id = getattr(inference_tx.payload, "dataset_id", None)

        quorum = select_quorum(
            request_id = request_id,
            block_hash = tip.hash,
            eligible   = dnn_nodes,
            model_name = None if model_hint == "any" else model_hint,
            dataset_id = dataset_id,
        )

        if quorum is None:
            # Not enough eligible nodes — fall back: use all DNN validators
            log.warning(
                "QoI quorum: too few eligible DNN nodes (%d) for request %s… — using all",
                len(dnn_nodes), request_id[:12],
            )
            quorum_nodes  = dnn_nodes
            quorum_f_val  = self.f
        else:
            quorum_nodes  = list(quorum.nodes)
            quorum_f_val  = quorum.f
            log.info(
                "QoI quorum elected: size=%d f=%d threshold=%d seed=%s… request=%s…",
                quorum.quorum_size, quorum.f, quorum.threshold,
                quorum.seed[:12], request_id[:12],
            )

        self._active_quorum = quorum

        # ── S-BFT membership check — skip if not in quorum ───────────────────
        quorum_ids = {n.node_id for n in quorum_nodes}
        if self.node_id not in quorum_ids:
            log.debug(
                "Not in QoI quorum for request %s… — standing by",
                request_id[:12],
            )
            await asyncio.sleep(BLOCK_TIME_TARGET)
            return

        # ── Select primary from quorum members only ───────────────────────────
        primary_id = select_proposer(
            nodes           = quorum_nodes,
            stakes          = dict(state.stakes),
            reputations     = dict(state.reputations),
            prev_block_hash = tip.hash,
            view            = self._current_view,
        )
        if primary_id is None:
            await asyncio.sleep(BLOCK_TIME_TARGET)
            return

        # Pop the inference tx — this node is participating
        self.svc.mempool.next_inference()
        self._pending_inference_tx = inference_tx
        self._round_seq += 1

        log.debug(
            "QoI round seq=%d primary=%s… quorum_f=%d",
            self._round_seq, primary_id[:8], quorum_f_val,
        )

        # Run inference on this node
        own_probs = await self._run_inference(image_hash)

        # Initialise QoI state machine with quorum-local f
        self._qoi_sm = QoIStateMachine(
            node_id    = self.node_id,
            primary_id = primary_id,
            f          = quorum_f_val,
        )
        # Register elected quorum so it's embedded in ConsensusOutcome
        self._qoi_sm.set_elected_quorum(frozenset(quorum_ids))
        self._round_start = now()

        pre_prepare = self._qoi_sm.start_round(
            request_id = request_id,
            image_hash = image_hash,
            seq        = self._round_seq,
            own_probs  = own_probs,
        )
        if pre_prepare:
            await self._broadcast_consensus("QOI_MSG", pre_prepare.to_dict())

        # Wait for committed outcome
        committed = await self._wait_for_qoi_commit()
        if committed:
            self._current_view = 0
        else:
            self._current_view += 1
            # Put inference tx back in the queue for the next round
            self.svc.mempool.add(inference_tx)
            log.info("QoI timeout — inference request re-queued")

        elapsed = now() - self._round_start
        sleep_for = max(0.0, BLOCK_TIME_TARGET - elapsed)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

    def attach_image_store(self, image_store) -> None:
        """Wire the content-addressed image store (ImageStore)."""
        self._image_store = image_store

    async def _run_inference(self, image_hash: str) -> list[float]:
        """
        Run the DNN model on the image identified by image_hash.

        Fetch order:
          1. Check local ImageStore.
          2. If missing, broadcast IMAGE_REQUEST over P2P and wait up to 8s
             for any peer to respond with the bytes.
          3. If still missing, fall back to a uniform distribution
             (round will likely be Byzantine-detected by other nodes).
        """
        image_store = getattr(self, "_image_store", None)
        if self.model is None:
            return [0.1] * 10

        # ── Step 1: local store ───────────────────────────────────────────────
        tensor = None
        if image_store is not None:
            try:
                tensor = await asyncio.get_event_loop().run_in_executor(
                    None, image_store.get_tensor, image_hash
                )
            except Exception as e:
                log.warning("Local image load failed %s: %s", image_hash[:12], e)

        # ── Step 2: P2P fetch if not local ────────────────────────────────────
        if tensor is None and self._p2p is not None:
            log.info("Image %s… not local — fetching from peers", image_hash[:12])
            raw = await self._p2p.fetch_image(image_hash)
            if raw is not None and image_store is not None:
                # fetch_image already stored it; reload as tensor
                try:
                    tensor = await asyncio.get_event_loop().run_in_executor(
                        None, image_store.get_tensor, image_hash
                    )
                except Exception as e:
                    log.warning("Tensor load after fetch failed %s: %s", image_hash[:12], e)

        # ── Step 3: run inference or fall back ────────────────────────────────
        if tensor is not None:
            try:
                probs, _ = self.model.predict(tensor)
                return list(probs)
            except Exception as e:
                log.warning("Inference failed for %s: %s", image_hash[:12], e)

        log.warning("Image %s unavailable — using uniform probs (node may be penalised)", image_hash[:12])
        return [0.1] * 10

    async def _wait_for_qoi_commit(self) -> bool:
        deadline = now() + VIEW_CHANGE_TIMEOUT
        while now() < deadline:
            if self._qoi_sm and self._qoi_sm.outcome is not None:
                await self._commit_qoi_block(self._qoi_sm.outcome)
                return True
            # Check timeout inside the SM
            if self._qoi_sm:
                vc = self._qoi_sm.check_timeout([0.1] * 10)
                if vc:
                    await self._broadcast_consensus("QOI_MSG", vc.to_dict())
            await asyncio.sleep(0.05)
        return False

    async def _commit_qoi_block(self, outcome: ConsensusOutcome) -> None:
        """Seal a QoI block into the chain."""
        # ── S-BFT quorum validation ───────────────────────────────────────────
        # Verify that every node that committed was actually in the elected quorum.
        # Any node outside the quorum has no authority to commit for this round.
        if outcome.elected_quorum:
            outsiders = [
                node_id
                for node_id, _ in outcome.commit_signatures
                if node_id not in outcome.elected_quorum
            ]
            if outsiders:
                log.warning(
                    "QoI commit contains %d node(s) outside elected quorum — "
                    "stripping: %s",
                    len(outsiders),
                    [n[:8] + "…" for n in outsiders],
                )
                # Strip their signatures — do not reward them
                outcome.commit_signatures = [
                    (nid, sig)
                    for nid, sig in outcome.commit_signatures
                    if nid in outcome.elected_quorum
                ]

        chain     = self.svc.chain
        nonces    = {a: chain.state.nonce_of(a) for a in chain.state.nonces}
        simple_txs = self.svc.mempool.select_simple(nonces, MAX_SIMPLE_TXS)
        block_fees = sum(tx.fee for tx in simple_txs)

        block = build_qoi_block(
            prev_hash    = chain.tip.hash,
            height       = chain.height + 1,
            proposer_id  = outcome.primary_id,
            inference_tx = self._pending_inference_tx,
            simple_txs   = simple_txs,
            outcome      = outcome,
            block_fees   = block_fees,
        )
        result = await self.svc.ingest_block(block)
        if result["accepted"]:
            # Apply reputation deltas from QoI scoring
            rep_deltas = {
                nr.node_id: nr.rep_delta
                for nr in outcome.round_result.node_results
            }
            chain.apply_reputation_deltas(rep_deltas)
            log.info(
                "QoI block committed height=%d class=%d quorum=%d hash=%s…",
                block.height, outcome.consensus_class,
                len(outcome.elected_quorum) if outcome.elected_quorum else -1,
                block.hash[:12],
            )
            if self._p2p:
                await self._p2p.broadcast_block(block.to_dict())
        else:
            log.warning("QoI block rejected: %s", result["reason"])

        self._pending_inference_tx = None
        self._qoi_sm = None

    # ══════════════════════════════════════════════════════════════════════════
    # Incoming message handler (called by P2P layer)
    # ══════════════════════════════════════════════════════════════════════════

    async def handle_consensus_msg(self, msg_type: str, data: dict) -> None:
        """
        Route an incoming consensus message from a peer to the active SM.
        Called by P2PServer._on_consensus().
        """
        try:
            if msg_type == "POS_BLOCK":
                await self._handle_incoming_pos_block(data)

            elif msg_type == "POS_VOTE":
                await self._handle_incoming_pos_vote(data)

            elif msg_type == "QOI_MSG":
                await self._handle_incoming_qoi_msg(data)

        except Exception as e:
            log.warning("handle_consensus_msg error (%s): %s", msg_type, e)

    async def _handle_incoming_pos_block(self, block_dict: dict) -> None:
        """A peer (the proposer) sent us a candidate PoS block — vote on it."""
        if self._pos_sm is None:
            return
        try:
            block = Block.from_dict(block_dict)
        except Exception as e:
            log.debug("Bad PoS block from peer: %s", e)
            return

        vote = self._pos_sm.handle_proposed_block(block)
        if vote:
            self._pending_pos_block = block
            await self._broadcast_consensus("POS_VOTE", vote.to_dict())

    async def _handle_incoming_pos_vote(self, vote_dict: dict) -> None:
        """A peer sent a PoS vote — feed it into our state machine."""
        if self._pos_sm is None:
            return
        vote = VoteMsg(
            node_id    = vote_dict["node_id"],
            block_hash = vote_dict["block_hash"],
            view       = vote_dict["view"],
            signature  = vote_dict.get("signature", ""),
            timestamp  = vote_dict.get("timestamp", now()),
        )
        reached = self._pos_sm.handle_vote(vote)
        if reached and self._pos_sm.outcome:
            await self._commit_pos_block(self._pos_sm.outcome)

    async def _handle_incoming_qoi_msg(self, msg_dict: dict) -> None:
        """A peer sent a QoI protocol message — feed it into the QoI SM."""
        if self._qoi_sm is None:
            return
        try:
            msg = message_from_dict(msg_dict)
        except Exception as e:
            log.debug("Bad QoI message: %s", e)
            return

        response = self._qoi_sm.handle_message(msg)
        if response:
            await self._broadcast_consensus("QOI_MSG", response.to_dict())

        if self._qoi_sm.outcome:
            await self._commit_qoi_block(self._qoi_sm.outcome)

    # ── Gossip helper ─────────────────────────────────────────────────────────

    async def _broadcast_consensus(self, msg_type: str, data: dict) -> None:
        if self._p2p:
            await self._p2p.broadcast_consensus(msg_type, data)
