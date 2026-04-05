"""
LLM Provider abstraction.

All providers implement the same LLMProvider interface so the orchestrator
doesn't care whether it's talking to OpenAI, a local Ollama instance, or a
mock for tests.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ═════════════════════════════════════════════════════════════════════════════
# Base interface
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class LLMMessage:
    role:    str   # "system" | "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """
    Abstract LLM provider.  Implement complete() to add a new backend.
    """

    @abstractmethod
    async def complete(
        self,
        messages:    list[LLMMessage],
        temperature: float = 0.0,
        max_tokens:  int   = 512,
    ) -> str:
        """
        Send a list of messages and return the assistant's reply as a string.
        temperature=0.0 → deterministic (required for routing/analysis tasks).
        """

    def name(self) -> str:
        return self.__class__.__name__


# ═════════════════════════════════════════════════════════════════════════════
# OpenAI provider
# ═════════════════════════════════════════════════════════════════════════════

class OpenAIProvider(LLMProvider):
    """
    OpenAI Chat Completions API.

    Requires:
        pip install openai
        OPENAI_API_KEY environment variable (or pass api_key directly)

    Usage:
        provider = OpenAIProvider(model="gpt-4o-mini")
    """

    def __init__(
        self,
        model:   str            = "gpt-4o-mini",
        api_key: str | None     = None,
        base_url: str | None    = None,
    ) -> None:
        self.model    = model
        self.api_key  = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url

    async def complete(
        self,
        messages:    list[LLMMessage],
        temperature: float = 0.0,
        max_tokens:  int   = 512,
    ) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install openai"
            )
        client = AsyncOpenAI(
            api_key  = self.api_key,
            base_url = self.base_url,
        )
        resp = await client.chat.completions.create(
            model       = self.model,
            messages    = [{"role": m.role, "content": m.content} for m in messages],
            temperature = temperature,
            max_tokens  = max_tokens,
        )
        return resp.choices[0].message.content.strip()


# ═════════════════════════════════════════════════════════════════════════════
# Ollama provider  (local, no API key required)
# ═════════════════════════════════════════════════════════════════════════════

class OllamaProvider(LLMProvider):
    """
    Local Ollama instance (https://ollama.com).

    Requires:
        ollama running locally (ollama serve)
        Model pulled: e.g. ollama pull llama3.2

    Usage:
        provider = OllamaProvider(model="llama3.2")
    """

    def __init__(
        self,
        model:    str = "llama3.2",
        host:     str = "http://localhost:11434",
    ) -> None:
        self.model = model
        self.host  = host.rstrip("/")

    async def complete(
        self,
        messages:    list[LLMMessage],
        temperature: float = 0.0,
        max_tokens:  int   = 512,
    ) -> str:
        try:
            import aiohttp
        except ImportError:
            raise ImportError(
                "aiohttp required for OllamaProvider. Install with: pip install aiohttp"
            )

        payload = {
            "model":   self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream":  False,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.host}/api/chat",
                json    = payload,
                timeout = aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["message"]["content"].strip()


# ═════════════════════════════════════════════════════════════════════════════
# Mock provider  (deterministic, for tests)
# ═════════════════════════════════════════════════════════════════════════════

class MockProvider(LLMProvider):
    """
    Deterministic mock for unit tests.

    Returns a fixed JSON reply that matches the schema expected by the
    orchestrator tools (routing, anomaly, decomposition).
    """

    def __init__(self, fixed_reply: str | None = None) -> None:
        self._fixed = fixed_reply

    async def complete(
        self,
        messages:    list[LLMMessage],
        temperature: float = 0.0,
        max_tokens:  int   = 512,
    ) -> str:
        if self._fixed:
            return self._fixed

        # Infer task from system prompt keyword
        system = messages[0].content if messages else ""

        if "routing" in system.lower():
            return json.dumps({
                "model_hint":  "any",
                "dataset_id":  "cifar10",
                "description": "Mock routing: no specific model required.",
                "confidence":  0.9,
            })

        if "anomaly" in system.lower():
            return json.dumps({
                "anomalous_nodes": [],
                "reason":          "Mock anomaly check: no anomalies detected.",
                "recommend_pom":   [],
            })

        if "decompose" in system.lower():
            return json.dumps({
                "subtasks": [
                    {"description": "Single classification task", "model_hint": "any"}
                ],
                "strategy": "sequential",
            })

        return json.dumps({"result": "mock ok", "reasoning": "mock provider"})
