"""
BlockBuilder — assembles a Block from consensus outcomes.

Two builders:
  build_qoi_block   — inference block produced after a QoI round
  build_pos_block   — simple block produced after a PoS vote round

Both are pure functions: given inputs → Block, no side effects.
The ConsensusEngine calls these once 2f+1 consensus is reached.
"""

from __future__ import annotations

from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.transaction import Transaction
from core.blockchain.utils import compute_merkle_root, now
from core.qoi.state_machine import ConsensusOutcome
from core.qoi.pos_consensus import PoSOutcome


def build_qoi_block(
    prev_hash:    str,
    height:       int,
    proposer_id:  str,
    inference_tx: Transaction,
    simple_txs:   list[Transaction],
    outcome:      ConsensusOutcome,
    block_fees:   float = 0.0,
) -> Block:
    """
    Assemble a QoI (inference) block after a completed QoI consensus round.

    Args:
        prev_hash:    hash of the last committed block
        height:       this block's height
        proposer_id:  the primary node that drove this round
        inference_tx: the INFERENCE_REQUEST tx that triggered this round
        simple_txs:   mempool simple txs to include
        outcome:      completed ConsensusOutcome from QoIStateMachine
        block_fees:   total fees from simple_txs (for reward computation)
    """
    # Rebuild outcome with actual block fees so rewards are correct
    from core.qoi.quality import compute_round_rewards
    round_result = compute_round_rewards(
        request_id      = outcome.request_id,
        primary_id      = outcome.primary_id,
        consensus_class = outcome.consensus_class,
        node_responses  = {
            nr.node_id: (nr.predicted_class, nr.probabilities)
            for nr in outcome.round_result.node_results
        },
        block_fees = block_fees,
    )
    final_outcome = ConsensusOutcome(
        request_id        = outcome.request_id,
        consensus_class   = outcome.consensus_class,
        view              = outcome.view,
        seq               = outcome.seq,
        primary_id        = outcome.primary_id,
        round_result      = round_result,
        commit_signatures = outcome.commit_signatures,
    )

    system_txs = final_outcome.build_system_txs(block_proposer=proposer_id)

    # Canonical tx order: inference → simple → system
    all_txs = [inference_tx] + simple_txs + system_txs
    merkle_root = compute_merkle_root(all_txs)

    header = BlockHeader(
        prev_hash   = prev_hash,
        height      = height,
        timestamp   = now(),
        proposer_id = proposer_id,
        merkle_root = merkle_root,
        block_type  = BlockType.QOI,
        view        = outcome.view,
    )

    proof = ConsensusProof(
        consensus_type = BlockType.QOI,
        view           = outcome.view,
    )
    for node_id, sig in outcome.commit_signatures:
        proof.add_signature(node_id, sig)

    return Block(
        header          = header,
        simple_txs      = simple_txs,
        consensus_proof = proof,
        inference_tx    = inference_tx,
        system_txs      = system_txs,
    )


def build_pos_block(
    prev_hash:   str,
    height:      int,
    simple_txs:  list[Transaction],
    outcome:     PoSOutcome,
) -> Block:
    """
    Assemble a PoS (simple) block after a completed PoS vote round.

    Args:
        prev_hash:  hash of the last committed block
        height:     this block's height
        simple_txs: the transactions sealed in this block
        outcome:    completed PoSOutcome from PoSConsensusMachine
    """
    merkle_root = compute_merkle_root(simple_txs)

    header = BlockHeader(
        prev_hash   = prev_hash,
        height      = height,
        timestamp   = now(),
        proposer_id = outcome.proposer_id,
        merkle_root = merkle_root,
        block_type  = BlockType.POS,
        view        = outcome.block.header.view,
    )

    proof = outcome.consensus_proof()

    return Block(
        header          = header,
        simple_txs      = simple_txs,
        consensus_proof = proof,
        inference_tx    = None,
        system_txs      = [],
    )
