"""Claude (Anthropic) LLM client with tier auto-selection and audit logging."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from trg.config.settings import Settings, get_settings
from trg.llm.tokens import estimate_cost_usd


@dataclass
class ClaudeCall:
    """Record of a single Claude API call."""

    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    prompt_hash: str
    response_text: str
    cost_usd: float


class ClaudeClient:
    """Thin wrapper around the Anthropic SDK with cost + audit hooks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=self.settings.anthropic_api_key or "missing",
            default_headers={
                "anthropic-beta": self.settings.anthropic_beta,
            },
        )

    def hash_prompt(self, system: str, messages: list[dict[str, str]]) -> str:
        """Stable hash of the prompt payload (for audit log)."""
        h = hashlib.sha256()
        h.update(system.encode("utf-8"))
        for msg in messages:
            h.update(msg.get("role", "").encode("utf-8"))
            h.update(b"\x00")
            h.update(msg.get("content", "").encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    async def complete(
        self,
        *,
        tier: str = "haiku",
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        project_id: str = "",
        agent_id: str = "",
        retrieved_chunk_ids: list[str] | None = None,
        extended_thinking: bool = False,
    ) -> tuple[str, ClaudeCall]:
        """Call Claude and return (response_text, call_record).

        `tier` is one of: haiku, sonnet, sonnet-thinking.
        """
        model = self._model_for_tier(tier)
        max_tokens = max_tokens or self.settings.max_claude_tokens_per_response

        kwargs: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if tier == "sonnet-thinking" or extended_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}

        prompt_hash = self.hash_prompt(system, messages)
        start = time.perf_counter()

        response = await self._client.messages.create(**kwargs)

        duration_ms = int((time.perf_counter() - start) * 1000)

        # Extract response text (skipping thinking blocks if present)
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        response_text = "\n".join(text_parts)

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost = estimate_cost_usd(model, in_tok, out_tok)

        return response_text, ClaudeCall(
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            duration_ms=duration_ms,
            prompt_hash=prompt_hash,
            response_text=response_text,
            cost_usd=cost,
        )

    def _model_for_tier(self, tier: str) -> str:
        return {
            "haiku": self.settings.anthropic_model_haiku,
            "sonnet": self.settings.anthropic_model_sonnet,
            "sonnet-thinking": self.settings.anthropic_model_sonnet_thinking,
        }.get(tier, self.settings.anthropic_model_haiku)
