"""
Protocol constants for InferenceChain.
All tuneable parameters live here — nowhere else.
"""

# ── Token ─────────────────────────────────────────────────────────────────────
TOKEN_NAME          = "INFER"
TOTAL_SUPPLY        = 100_000_000.0     # 100M INFER max supply
GENESIS_ALLOCATION  = 10_000_000.0      # tokens minted at genesis

# ── Staking ───────────────────────────────────────────────────────────────────
MIN_STAKE           = 1_000.0           # minimum INFER to register as a node
SLASH_PENALTY       = 100.0             # INFER slashed per Byzantine behaviour

# ── Block ─────────────────────────────────────────────────────────────────────
MAX_SIMPLE_TXS      = 50                # max simple transactions per block
BLOCK_TIME_TARGET   = 5.0              # seconds between blocks (target)

# ── BFT Consensus ─────────────────────────────────────────────────────────────
# Network can tolerate f Byzantine nodes out of n total (n >= 3f+1)
DEFAULT_F           = 1                 # default fault tolerance
VIEW_CHANGE_TIMEOUT = 10.0             # seconds before triggering view change

# ── Inference / QoI ───────────────────────────────────────────────────────────
NUM_CLASSES         = 10                # CIFAR-10
INFERENCE_REWARD    = 10.0             # INFER minted per consensus round (block reward)
MIN_CONFIDENCE      = 0.5              # minimum softmax confidence to accept result
LEADER_BONUS        = 2.0              # extra INFER for the primary that drove consensus

# ── Reputation ────────────────────────────────────────────────────────────────
INITIAL_REPUTATION  = 0.0              # reputation at node registration
REP_CAP_PER_ROUND   = 0.5             # max reputation gain per consensus round
REP_PENALTY         = 0.3             # reputation loss per Byzantine act
REP_LEADER_BONUS    = 0.1             # extra rep for primary on top of QoI-proportional gain

# ── QoI Scoring ───────────────────────────────────────────────────────────────
QOI_HONEST_THRESHOLD = 0.0            # cosine sim floor — all argmax-correct nodes rewarded
                                       # (set > 0 to require minimum quality)

# ── Proof of Model (PoM) ──────────────────────────────────────────────────────
POM_CHALLENGE_SIZE    = 50             # number of challenge samples issued
MIN_MODEL_ACCURACY    = 0.80           # node must score ≥ 80% on challenge
POM_VERIFY_TIMEOUT    = 30.0          # seconds validators have to submit MODEL_VERIFY
MIN_STAKE_DNN         = 1_000.0       # minimum stake for DNN validator (same as MIN_STAKE)
MIN_STAKE_POS         = 500.0         # minimum stake for PoS-only validator (lower bar)
SUPPORTED_DATASETS    = {"cifar10"}   # expandable in future

# ── Node types ────────────────────────────────────────────────────────────────
NODE_TYPE_DNN = "dnn"
NODE_TYPE_POS = "pos"

# ── Mempool ───────────────────────────────────────────────────────────────────
MEMPOOL_MAX_SIZE    = 10_000           # max pending transactions

# ── VM ────────────────────────────────────────────────────────────────────────
CONTRACT_GAS_LIMIT  = 1_000_000        # max opcodes per contract call
