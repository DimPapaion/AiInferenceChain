"""
Unit tests for core/qoi/ — messages, quality scoring, proposer, state machine, PoS.
"""

import math
import pytest

from core.qoi import (
    MsgType, PrePrepareMsg, PrepareMsg, CommitMsg, ViewChangeMsg, NewViewMsg,
    message_from_dict,
    cosine_similarity, aggregate_probabilities, compute_round_rewards,
    NodeQoIResult, RoundResult,
    select_proposer, compute_weights,
    QoIPhase, QoIStateMachine, ConsensusOutcome,
    PoSPhase, PoSConsensusMachine, VoteMsg,
)
from core.blockchain import (
    create_genesis_block, Chain,
    NodeRegisterPayload, StakePayload, Transaction, TxType,
    Block, BlockHeader, BlockType, ConsensusProof,
    compute_merkle_root, now,
    MIN_STAKE, INFERENCE_REWARD, LEADER_BONUS,
)
from core.blockchain.chain import NodeInfo

NODE_A = "a" * 40
NODE_B = "b" * 40
NODE_C = "c" * 40
NODE_D = "d" * 40
PREV_HASH = "0" * 64


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_node(node_id: str, model: str = "resnet20") -> NodeInfo:
    return NodeInfo(
        node_id=node_id, address=node_id, node_type="dnn",
        public_key="aa"*32, endpoint="127.0.0.1:8000", registered_at=0,
    )

def uniform_probs(n=10) -> list[float]:
    return [1.0 / n] * n

def peaked_probs(cls: int, confidence: float, n: int = 10) -> list[float]:
    """Probability vector heavily peaked at cls."""
    rest = (1.0 - confidence) / (n - 1)
    return [confidence if i == cls else rest for i in range(n)]


# ═════════════════════════════════════════════════════════════════════════════
# Messages
# ═════════════════════════════════════════════════════════════════════════════

class TestMessages:
    def test_pre_prepare_roundtrip(self):
        msg = PrePrepareMsg(
            msg_type=MsgType.PRE_PREPARE, view=1, seq=0,
            sender_id=NODE_A, request_id="req-1",
            image_hash="f"*64, probabilities=peaked_probs(3, 0.9),
            predicted_class=3,
        )
        restored = message_from_dict(msg.to_dict())
        assert restored.predicted_class == 3
        assert restored.request_id == "req-1"

    def test_prepare_roundtrip(self):
        msg = PrepareMsg(
            msg_type=MsgType.PREPARE, view=1, seq=0,
            sender_id=NODE_B, request_id="req-1",
            probabilities=peaked_probs(3, 0.8), predicted_class=3,
        )
        restored = message_from_dict(msg.to_dict())
        assert restored.predicted_class == 3

    def test_commit_roundtrip(self):
        msg = CommitMsg(
            msg_type=MsgType.COMMIT, view=1, seq=0,
            sender_id=NODE_A, request_id="req-1", consensus_class=3,
        )
        restored = message_from_dict(msg.to_dict())
        assert restored.consensus_class == 3

    def test_view_change_roundtrip(self):
        msg = ViewChangeMsg(
            msg_type=MsgType.VIEW_CHANGE, view=1, seq=0,
            sender_id=NODE_A, new_view=2, last_seq=0,
        )
        restored = message_from_dict(msg.to_dict())
        assert restored.new_view == 2

    def test_msg_id_is_deterministic(self):
        msg = PrepareMsg(
            msg_type=MsgType.PREPARE, view=1, seq=0,
            sender_id=NODE_A, request_id="r",
            probabilities=[0.1]*10, predicted_class=0,
            timestamp=1234567890.0,
        )
        assert msg.msg_id == msg.msg_id   # stable


# ═════════════════════════════════════════════════════════════════════════════
# Quality scoring
# ═════════════════════════════════════════════════════════════════════════════

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = peaked_probs(3, 0.9)
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        # Two peaked vectors at different classes — nearly orthogonal
        a = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_returns_in_zero_one(self):
        v1 = peaked_probs(2, 0.7)
        v2 = peaked_probs(2, 0.5)
        score = cosine_similarity(v1, v2)
        assert 0.0 <= score <= 1.0

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0]*10, [0.1]*10) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            cosine_similarity([0.1]*10, [0.1]*5)


class TestAggregateProbs:
    def test_mean_of_identical(self):
        v = peaked_probs(3, 0.9)
        agg = aggregate_probabilities([v, v, v])
        assert agg == pytest.approx(v)

    def test_mean_computation(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        agg = aggregate_probabilities([a, b])
        assert agg == pytest.approx([0.5, 0.5])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            aggregate_probabilities([])


class TestComputeRoundRewards:
    def _responses(self, honest_class=3, n_honest=3, n_byzantine=1):
        responses = {}
        for i in range(n_honest):
            nid = hex(i)[2:].zfill(40)
            responses[nid] = (honest_class, peaked_probs(honest_class, 0.85))
        for i in range(n_byzantine):
            nid = hex(100 + i)[2:].zfill(40)
            responses[nid] = (honest_class + 1, peaked_probs(honest_class + 1, 0.6))
        return responses

    def test_honest_nodes_rewarded(self):
        responses = self._responses(n_honest=3, n_byzantine=1)
        primary   = list(responses.keys())[0]
        result    = compute_round_rewards("req-1", primary, 3, responses, block_fees=0.0)
        for nr in result.honest_nodes:
            assert nr.token_reward > 0.0

    def test_byzantine_nodes_not_rewarded(self):
        responses = self._responses(n_honest=3, n_byzantine=1)
        primary   = list(responses.keys())[0]
        result    = compute_round_rewards("req-1", primary, 3, responses, block_fees=0.0)
        for nr in result.byzantine_nodes:
            assert nr.token_reward == 0.0

    def test_total_distributed_equals_pool(self):
        responses = self._responses(n_honest=3, n_byzantine=0)
        primary   = list(responses.keys())[0]
        block_fees = 5.0
        result     = compute_round_rewards("req-1", primary, 3, responses, block_fees)
        total_rewarded = sum(nr.token_reward for nr in result.node_results)
        expected_pool  = block_fees + INFERENCE_REWARD + LEADER_BONUS
        assert total_rewarded == pytest.approx(expected_pool, rel=1e-6)

    def test_primary_gets_leader_bonus(self):
        responses = {}
        responses[NODE_A] = (3, peaked_probs(3, 0.9))
        responses[NODE_B] = (3, peaked_probs(3, 0.9))
        responses[NODE_C] = (3, peaked_probs(3, 0.9))
        result_a = compute_round_rewards("r", NODE_A, 3, responses)
        result_b = compute_round_rewards("r", NODE_B, 3, responses)
        reward_as_primary    = next(r.token_reward for r in result_a.node_results if r.node_id == NODE_A)
        reward_as_non_primary = next(r.token_reward for r in result_b.node_results if r.node_id == NODE_A)
        assert reward_as_primary > reward_as_non_primary

    def test_higher_confidence_higher_reward(self):
        # Majority (NODE_A, NODE_C, NODE_D) are high-confidence → aggregate is high-confidence.
        # NODE_B has lower confidence → its cosine sim with the aggregate is lower → lower reward.
        # NODE_D is primary so its leader bonus doesn't affect the NODE_A vs NODE_B comparison.
        responses = {
            NODE_A: (3, peaked_probs(3, 0.95)),   # high confidence
            NODE_B: (3, peaked_probs(3, 0.52)),   # low confidence
            NODE_C: (3, peaked_probs(3, 0.93)),   # high confidence
            NODE_D: (3, peaked_probs(3, 0.91)),   # high confidence (primary)
        }
        result = compute_round_rewards("r", NODE_D, 3, responses)
        rA = next(r.token_reward for r in result.node_results if r.node_id == NODE_A)
        rB = next(r.token_reward for r in result.node_results if r.node_id == NODE_B)
        assert rA > rB

    def test_reputation_capped_per_round(self):
        from core.blockchain.constants import REP_CAP_PER_ROUND
        responses = {NODE_A: (3, peaked_probs(3, 0.99))}
        result    = compute_round_rewards("r", NODE_A, 3, responses)
        nr        = result.node_results[0]
        # rep delta must not exceed cap + leader bonus
        from core.blockchain.constants import REP_LEADER_BONUS
        assert nr.rep_delta <= REP_CAP_PER_ROUND + REP_LEADER_BONUS + 1e-9

    def test_byzantine_gets_rep_penalty(self):
        from core.blockchain.constants import REP_PENALTY
        responses = {
            NODE_A: (3, peaked_probs(3, 0.9)),
            NODE_B: (3, peaked_probs(3, 0.9)),
            NODE_C: (3, peaked_probs(3, 0.9)),
            NODE_D: (5, peaked_probs(5, 0.7)),   # Byzantine
        }
        result = compute_round_rewards("r", NODE_A, 3, responses)
        nr_d   = next(r for r in result.node_results if r.node_id == NODE_D)
        assert nr_d.rep_delta == pytest.approx(-REP_PENALTY)


# ═════════════════════════════════════════════════════════════════════════════
# Proposer selection
# ═════════════════════════════════════════════════════════════════════════════

class TestProposer:
    def _nodes(self):
        return [make_node(NODE_A), make_node(NODE_B), make_node(NODE_C)]

    def test_deterministic(self):
        nodes = self._nodes()
        stakes = {NODE_A: 1000.0, NODE_B: 1000.0, NODE_C: 1000.0}
        reps   = {NODE_A: 0.0, NODE_B: 0.0, NODE_C: 0.0}
        p1 = select_proposer(nodes, stakes, reps, "a"*64, view=0)
        p2 = select_proposer(nodes, stakes, reps, "a"*64, view=0)
        assert p1 == p2

    def test_different_views_may_differ(self):
        nodes = self._nodes()
        stakes = {NODE_A: 1000.0, NODE_B: 1000.0, NODE_C: 1000.0}
        reps   = {NODE_A: 0.0, NODE_B: 0.0, NODE_C: 0.0}
        results = {select_proposer(nodes, stakes, reps, "a"*64, view=v) for v in range(20)}
        # With 3 equal-weight nodes, multiple views should elect different primaries
        assert len(results) > 1

    def test_higher_stake_elected_more(self):
        nodes  = self._nodes()
        stakes = {NODE_A: 10_000.0, NODE_B: 100.0, NODE_C: 100.0}
        reps   = {NODE_A: 0.0, NODE_B: 0.0, NODE_C: 0.0}
        elections = [select_proposer(nodes, stakes, reps, str(v)*64, v) for v in range(100)]
        assert elections.count(NODE_A) > elections.count(NODE_B)

    def test_higher_rep_amplifies_selection(self):
        nodes  = self._nodes()
        stakes = {NODE_A: 1000.0, NODE_B: 1000.0, NODE_C: 1000.0}
        reps   = {NODE_A: 10.0, NODE_B: 0.0, NODE_C: 0.0}
        elections = [select_proposer(nodes, stakes, reps, str(v)*64, v) for v in range(100)]
        assert elections.count(NODE_A) > elections.count(NODE_B)

    def test_no_nodes_returns_none(self):
        assert select_proposer([], {}, {}, "a"*64, 0) is None

    def test_compute_weights(self):
        nodes  = [make_node(NODE_A), make_node(NODE_B)]
        stakes = {NODE_A: 1000.0, NODE_B: 2000.0}
        reps   = {NODE_A: 1.0, NODE_B: 0.0}
        w = compute_weights(nodes, stakes, reps)
        # NODE_A: 1000 * (1 + 1.0) = 2000
        # NODE_B: 2000 * (1 + 0.0) = 2000
        assert w[NODE_A] == pytest.approx(2000.0)
        assert w[NODE_B] == pytest.approx(2000.0)


# ═════════════════════════════════════════════════════════════════════════════
# QoI State Machine
# ═════════════════════════════════════════════════════════════════════════════

class TestQoIStateMachine:
    def _make_cluster(self, n=4, f=1):
        """Create n state machines with node_0 as primary."""
        primary = hex(0)[2:].zfill(40)
        nodes   = [hex(i)[2:].zfill(40) for i in range(n)]
        sms     = {nid: QoIStateMachine(nid, primary, f=f) for nid in nodes}
        return sms, primary, nodes

    def _run_full_round(self, n=4, f=1, consensus_class=3):
        """Simulate a full consensus round with all honest nodes."""
        sms, primary, nodes = self._make_cluster(n, f)
        probs = peaked_probs(consensus_class, 0.9)

        # Start round — primary returns PRE_PREPARE
        pre_prepare = sms[primary].start_round("req-1", "f"*64, seq=0, own_probs=probs)
        assert pre_prepare is not None
        assert sms[primary].phase == QoIPhase.PRE_PREPARE

        # Replicas start round and handle PRE_PREPARE
        prepares = []
        for nid in nodes:
            if nid == primary:
                continue
            sms[nid].start_round("req-1", "f"*64, seq=0, own_probs=probs)
            prepare = sms[nid].handle_message(pre_prepare)
            if prepare:
                prepares.append(prepare)

        # Distribute PREPAREs to all nodes (including primary)
        commits = []
        for prepare in prepares:
            for nid in nodes:
                result = sms[nid].handle_message(prepare)
                if result and result.msg_type == MsgType.COMMIT:
                    if result not in commits:
                        commits.append(result)

        # Distribute COMMITs
        for commit in commits:
            for nid in nodes:
                sms[nid].handle_message(commit)

        return sms, primary, nodes

    def test_full_round_reaches_committed(self):
        sms, primary, nodes = self._run_full_round(n=4, f=1, consensus_class=3)
        # All nodes should be COMMITTED
        for nid in nodes:
            assert sms[nid].phase == QoIPhase.COMMITTED, f"{nid} stuck in {sms[nid].phase}"

    def test_outcome_has_correct_class(self):
        sms, primary, nodes = self._run_full_round(n=4, f=1, consensus_class=5)
        for nid in nodes:
            if sms[nid].outcome:
                assert sms[nid].outcome.consensus_class == 5

    def test_outcome_builds_system_txs(self):
        sms, primary, nodes = self._run_full_round(n=4, f=1)
        outcome = sms[primary].outcome
        assert outcome is not None
        txs = outcome.build_system_txs()
        tx_types = [tx.tx_type for tx in txs]
        assert TxType.INFERENCE_RESPONSE in tx_types
        assert TxType.CONSENSUS_RESULT   in tx_types
        assert TxType.REWARD             in tx_types

    def test_view_change_triggered_on_timeout(self):
        sm = QoIStateMachine(NODE_A, NODE_B, f=1)
        sm.start_round("req-1", "f"*64, seq=0, own_probs=peaked_probs(3, 0.9))
        sm._phase_start = now() - 9999  # force timeout
        vc = sm.check_timeout(peaked_probs(3, 0.9))
        assert vc is not None
        assert vc.msg_type == MsgType.VIEW_CHANGE
        assert sm.phase == QoIPhase.VIEW_CHANGE

    def test_stale_message_ignored(self):
        sms, primary, nodes = self._make_cluster()
        sm = sms[nodes[1]]
        sm.start_round("req-1", "f"*64, seq=0, own_probs=peaked_probs(3, 0.9))
        old_prepare = PrepareMsg(
            msg_type=MsgType.PREPARE, view=0, seq=0,
            sender_id=NODE_C,
            request_id="req-1",
            probabilities=peaked_probs(3, 0.9),
            predicted_class=3,
        )
        sm.view = 5   # advance view
        result = sm.handle_message(old_prepare)
        assert result is None   # stale, ignored


# ═════════════════════════════════════════════════════════════════════════════
# PoS Consensus Machine
# ═════════════════════════════════════════════════════════════════════════════

class TestPoSConsensusMachine:
    def _make_pos_block(self):
        merkle = compute_merkle_root([])
        header = BlockHeader(
            prev_hash=PREV_HASH, height=1, timestamp=now(),
            proposer_id=NODE_A, merkle_root=merkle,
            block_type=BlockType.POS, view=0,
        )
        proof = ConsensusProof(BlockType.POS, view=0)
        return Block(header=header, simple_txs=[], consensus_proof=proof)

    def test_proposer_builds_and_votes(self):
        sm    = PoSConsensusMachine(NODE_A, NODE_A, f=1)
        block = self._make_pos_block()
        vote  = sm.propose_block(block)
        assert vote.block_hash == block.hash
        assert sm.phase == PoSPhase.PROPOSED

    def test_replica_votes_on_valid_block(self):
        sm    = PoSConsensusMachine(NODE_B, NODE_A, f=1)
        block = self._make_pos_block()
        vote  = sm.handle_proposed_block(block)
        assert vote is not None
        assert vote.node_id == NODE_B

    def test_2f_plus_1_votes_commits(self):
        f     = 1
        block = self._make_pos_block()
        sms   = {nid: PoSConsensusMachine(nid, NODE_A, f=f) for nid in [NODE_A, NODE_B, NODE_C]}
        votes = []

        # proposer votes
        votes.append(sms[NODE_A].propose_block(block))
        votes.append(sms[NODE_B].handle_proposed_block(block))
        votes.append(sms[NODE_C].handle_proposed_block(block))

        committed = False
        for vote in votes:
            for sm in sms.values():
                if sm.handle_vote(vote):
                    committed = True

        assert committed
        committed_sm = next(s for s in sms.values() if s.phase == PoSPhase.COMMITTED)
        assert committed_sm.outcome is not None
        proof = committed_sm.outcome.consensus_proof()
        assert proof.is_valid(f=1)

    def test_wrong_block_hash_vote_rejected(self):
        sm    = PoSConsensusMachine(NODE_A, NODE_A, f=1)
        block = self._make_pos_block()
        sm.propose_block(block)
        bad_vote = VoteMsg(node_id=NODE_B, block_hash="bad"*21, view=0)
        assert sm.handle_vote(bad_vote) is False


# ═════════════════════════════════════════════════════════════════════════════
# Chain reputation integration
# ═════════════════════════════════════════════════════════════════════════════

class TestChainReputation:
    def _make_chain_with_node(self):
        genesis = create_genesis_block(initial_allocations={NODE_A: 100_000.0})
        chain   = Chain(genesis, f=1)
        return chain

    def test_reputation_zero_at_registration(self):
        from core.blockchain.transaction import NodeRegisterPayload
        from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
        chain = self._make_chain_with_node()
        reg = Transaction(
            tx_type=TxType.NODE_REGISTER, sender=NODE_A,
            payload=NodeRegisterPayload("resnet20", "aa"*32, "127.0.0.1:8000"),
            nonce=1, fee=0.0,
        )
        merkle = compute_merkle_root([reg])
        header = BlockHeader(
            prev_hash=chain.tip.hash, height=1, timestamp=now(),
            proposer_id=NODE_A, merkle_root=merkle,
            block_type=BlockType.POS, view=0,
        )
        proof = ConsensusProof(BlockType.POS, view=0,
                               signatures=[(NODE_A,"s1"),(NODE_B,"s2"),(NODE_C,"s3")])
        block = Block(header=header, simple_txs=[reg], consensus_proof=proof)
        chain.append(block)
        assert chain.state.reputation_of(NODE_A) == pytest.approx(0.0)

    def test_apply_reputation_deltas(self):
        chain = self._make_chain_with_node()
        chain.state.reputations[NODE_A] = 1.0
        chain.apply_reputation_deltas({NODE_A: 0.4, NODE_B: -5.0})
        assert chain.state.reputation_of(NODE_A) == pytest.approx(1.4)
        assert chain.state.reputation_of(NODE_B) == pytest.approx(0.0)   # clamped at 0
