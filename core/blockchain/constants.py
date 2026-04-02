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

# ── Inference ─────────────────────────────────────────────────────────────────
NUM_CLASSES         = 10                # CIFAR-10
INFERENCE_REWARD    = 10.0             # INFER rewarded per honest inference
MIN_CONFIDENCE      = 0.5              # minimum softmax confidence to accept result

# ── Mempool ───────────────────────────────────────────────────────────────────
MEMPOOL_MAX_SIZE    = 10_000           # max pending transactions

# ── VM ────────────────────────────────────────────────────────────────────────
CONTRACT_GAS_LIMIT  = 1_000_000        # max opcodes per contract call
