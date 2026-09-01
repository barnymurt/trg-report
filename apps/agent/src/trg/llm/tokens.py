"""Cost estimation for Claude API calls.

Prices (per million tokens) — updated 2024-11. Adjust as Anthropic changes
pricing. See https://docs.anthropic.com/en/docs/about-claude/pricing.
"""

# USD per 1M tokens
PRICES: dict[str, dict[str, float]] = {
    "claude-3-5-haiku-latest":  {"input": 0.80,  "output": 4.00},
    "claude-3-5-sonnet-latest": {"input": 3.00,  "output": 15.00},
    "claude-3-opus-latest":     {"input": 15.00, "output": 75.00},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return approximate USD cost for a Claude call."""
    prices = PRICES.get(model, PRICES["claude-3-5-haiku-latest"])
    in_cost = (input_tokens / 1_000_000) * prices["input"]
    out_cost = (output_tokens / 1_000_000) * prices["output"]
    return round(in_cost + out_cost, 6)
