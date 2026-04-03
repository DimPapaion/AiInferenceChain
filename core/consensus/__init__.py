"""
core.consensus — Block production engine for InferenceChain.

Exports:
  ConsensusEngine  — main autonomous block-production loop
  build_pos_block  — assemble a PoS block from a PoS outcome
  build_qoi_block  — assemble a QoI block from a QoI outcome
"""

from core.consensus.engine import ConsensusEngine
from core.consensus.block_builder import build_pos_block, build_qoi_block

__all__ = ["ConsensusEngine", "build_pos_block", "build_qoi_block"]
