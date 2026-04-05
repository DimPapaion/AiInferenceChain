"""
core.llm — LLM Orchestration Layer for InferenceChain.

This layer sits ABOVE the blockchain and consensus layers.
It uses an LLM to make intelligent decisions about:
  1. Request routing — which model/dataset hint to attach
  2. Anomaly detection — flagging suspicious validator behaviour
  3. Parallel task decomposition — splitting complex jobs
  4. Chain state analysis — natural language Q&A over chain state

What it NEVER does:
  - Decide quorum membership (that stays deterministic in quorum.py)
  - Sign or submit transactions on behalf of users
  - Access private keys

The LLM is accessed via a provider-agnostic interface (LLMProvider ABC).
Built-in implementations:
  - OpenAIProvider   (via openai package, requires OPENAI_API_KEY)
  - OllamaProvider   (local, zero external dependency — recommended for testnet)
  - MockProvider     (deterministic, no network — used in tests)
"""

from core.llm.provider import LLMProvider, OpenAIProvider, OllamaProvider, MockProvider
from core.llm.orchestrator import InferenceOrchestrator

__all__ = [
    "LLMProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "MockProvider",
    "InferenceOrchestrator",
]
