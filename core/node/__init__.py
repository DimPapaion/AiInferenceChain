"""
core.node — Node identity, registration, and consensus participation.

Exports:
  NodeIdentity, pubkey_to_address, verify_signature, make_test_identity
  InferenceNode, NodeStatus, ModelHandle
  PoSNode, PoSNodeStatus
  generate_challenge_tx, generate_challenge_indices
  verify_model_response, tally_pom, PoMVerificationState
"""

from .identity import (
    NodeIdentity,
    pubkey_to_address,
    verify_signature,
    make_test_identity,
)
from .inference_node import InferenceNode, NodeStatus, ModelHandle
from .pos_node import PoSNode, PoSNodeStatus
from .pom import (
    generate_challenge_tx,
    generate_challenge_indices,
    verify_model_response,
    tally_pom,
    PoMVerificationState,
)

__all__ = [
    "NodeIdentity", "pubkey_to_address", "verify_signature", "make_test_identity",
    "InferenceNode", "NodeStatus", "ModelHandle",
    "PoSNode", "PoSNodeStatus",
    "generate_challenge_tx", "generate_challenge_indices",
    "verify_model_response", "tally_pom", "PoMVerificationState",
]
