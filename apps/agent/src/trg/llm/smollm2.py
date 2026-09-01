"""SmolLM2 client for local routing / compression / trivial Q&A.

SmolLM2 runs locally (no API cost). It's used to keep Claude tokens
focused on comprehension by handling:

  - Project / agent classification
  - Compressing retrieved context to ~3k tokens
  - Summarising long conversation history
  - Trivial Q&A that doesn't need Claude

Communicates with the llama.cpp server (OpenAI-compatible API).
"""

from __future__ import annotations

import httpx

from trg.config.settings import Settings, get_settings


class SmolLM2Client:
    """OpenAI-compatible client for the local SmolLM2 server."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.smollm2_url.rstrip("/")
        self.model = self.settings.smollm2_model
        self._client = httpx.AsyncClient(timeout=60.0)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        """Run a simple chat completion. Returns the assistant text."""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    async def classify_project(self, message: str, candidate_projects: list[str]) -> str:
        """Use SmolLM2 to decide which project a user message belongs to.

        Returns the project name (best of `candidate_projects`).
        Falls back to the first candidate if the model is uncertain.
        """
        if not candidate_projects:
            return ""
        system = (
            "You are a routing assistant. You classify a user's message into exactly one "
            "project from a fixed list. Respond with ONLY the project name, nothing else."
        )
        user = (
            f"Projects: {', '.join(candidate_projects)}\n\n"
            f"User message: {message}\n\n"
            f"Project:"
        )
        try:
            result = await self.complete(system=system, user=user, max_tokens=20)
            # Match to closest candidate (in case model adds punctuation)
            for p in candidate_projects:
                if p.lower() in result.lower():
                    return p
            return candidate_projects[0]
        except Exception:
            return candidate_projects[0]

    async def classify_difficulty(self, message: str) -> str:
        """Return one of: trivial, medium, hard, expert.

        Drives Claude tier auto-selection.
        """
        system = (
            "You classify the difficulty of a user request for an LLM agent.\n"
            "Respond with exactly one word: trivial, medium, hard, expert.\n"
            "- trivial: factual lookup, formatting, simple classification, list reordering\n"
            "- medium: summarisation, short Q&A, drafting with clear context\n"
            "- hard: multi-document synthesis, ambiguous requests, comparison\n"
            "- expert: novel reasoning, ethical nuance, planning across many constraints"
        )
        try:
            result = await self.complete(system=system, user=message, max_tokens=8)
            result = result.strip().lower()
            for tier in ("trivial", "medium", "hard", "expert"):
                if tier in result:
                    return tier
            return "medium"
        except Exception:
            return "medium"

    async def compress(
        self, chunks: list[str], target_tokens: int, query: str
    ) -> str:
        """Compress retrieved chunks to fit ~target_tokens, preserving evidence
        most relevant to the query."""
        joined = "\n\n---\n\n".join(chunks)
        system = (
            "You are an evidence compressor. Given a user query and several retrieved "
            "passages, produce a tight summary that preserves every fact, number, name, "
            "and citation needed to answer the query faithfully. Strip boilerplate. "
            "Cite each fact with [chunk-N] matching the passage index. Do not invent."
        )
        user = (
            f"Query: {query}\n\n"
            f"Target length: ~{target_tokens} tokens\n\n"
            f"Passages:\n{joined}\n\n"
            f"Compressed evidence:"
        )
        try:
            return await self.complete(
                system=system, user=user, max_tokens=target_tokens
            )
        except Exception:
            return joined

    async def close(self) -> None:
        await self._client.aclose()
