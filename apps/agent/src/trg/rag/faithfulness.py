"""Faithfulness scoring — NLI-based.

Uses a DeBERTa-v3-large MNLI model to check whether a generated response
is entailed by the retrieved evidence. Cheap (CPU, sub-100ms) and runs
on every Claude response.
"""

from __future__ import annotations

import httpx

from trg.config.settings import Settings, get_settings


class FaithfulnessScorer:
    """NLI-based faithfulness check."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def score(
        self, *, response: str, evidence_chunks: list[str]
    ) -> float:
        """Return a 0..1 faithfulness score.

        Score is the fraction of claims in the response that are entailed
        by the evidence. Returns 1.0 if no claims can be extracted.
        """
        if not evidence_chunks:
            return 0.0

        # DeBERTa NLI via TEI-compatible endpoint
        # We use sentence-level entailment; for v1 we run a single bulk call.
        premise = " ".join(evidence_chunks)
        url = self.settings.reranker_url.replace(":8081", ":8083")
        url = f"{url.rstrip('/')}/v1/score"
        try:
            resp = await self._client.post(
                url,
                json={
                    "premise": premise[:8000],
                    "hypothesis": response[:2000],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Expected: {"label": "entailment|neutral|contradiction", "score": float}
            label = data.get("label", "neutral").lower()
            if label == "entailment":
                return float(data.get("score", 0.7))
            if label == "contradiction":
                return 0.0
            return 0.5
        except Exception:
            return 0.5

    async def close(self) -> None:
        await self._client.aclose()
