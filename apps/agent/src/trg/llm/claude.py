"""Claude (Anthropic) LLM client with tier auto-selection and audit logging."""

from __future__ import annotations

import hashlib
import re
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
    """Thin wrapper around the Anthropic SDK with cost + audit hooks.

    Honours `trg_demo_mode` in settings: when true, returns canned
    responses that include realistic-looking ```action``` blocks so the
    full UI flow (chat → proposed actions → executor → artefact files)
    can be exercised without an API key or running services.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=self.settings.anthropic_api_key or "missing",
            default_headers={
                "anthropic-beta": self.settings.anthropic_beta,
            },
        )

    def hash_prompt(self, system: str, messages: list[dict[str, str]]) -> str:
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
        if self.settings.trg_demo_mode:
            return self._demo_complete(messages=messages)

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

    def _demo_complete(self, *, messages: list[dict[str, str]]) -> tuple[str, ClaudeCall]:
        """Return a canned response matching the user's last message."""
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "").lower()
                break

        response_text = _pick_demo_response(user_msg)

        # Fake usage numbers so the audit log looks plausible
        prompt_hash = self.hash_prompt(
            "demo-system", [{"role": "user", "content": user_msg}]
        )
        call = ClaudeCall(
            model="claude-3-5-haiku-latest (DEMO)",
            input_tokens=180 + len(user_msg) // 4,
            output_tokens=180 + len(response_text) // 4,
            duration_ms=12,
            prompt_hash=prompt_hash,
            response_text=response_text,
            cost_usd=0.0,
        )
        return response_text, call

    def _model_for_tier(self, tier: str) -> str:
        return {
            "haiku": self.settings.anthropic_model_haiku,
            "sonnet": self.settings.anthropic_model_sonnet,
            "sonnet-thinking": self.settings.anthropic_model_sonnet_thinking,
        }.get(tier, self.settings.anthropic_model_haiku)


# ─── Demo canned responses ─────────────────────────────────────────────

def _pick_demo_response(user_msg: str) -> str:
    """Match on keywords to pick a believable canned reply.

    Each reply includes an ```action``` block so the PWA surfaces a
    proposed action you can approve.
    """
    if any(k in user_msg for k in ["kitchen", "remodel", "cabinet", "counter", "tile", "sink", "range", "oven"]):
        return _DEMO_REMODEL
    if any(k in user_msg for k in ["appointment", "doctor", "consult", "hospital", "cardiology", "oncology", "scan", "mri"]):
        return _DEMO_APPOINTMENT
    if any(k in user_msg for k in ["husband", "partner"]):
        return _DEMO_HUSBAND
    if any(k in user_msg for k in ["agent", "create", "new project"]):
        return _DEMO_AGENT
    if any(k in user_msg for k in ["week", "digest", "summary", "what's new"]):
        return _DEMO_DIGEST
    return _DEMO_DEFAULT


_DEMO_REMODEL = """Here's what I found across your remodel documents:

- **Sink placement:** the Bosch sink spec sheet (p. 2) confirms a 762mm × 457mm cutout — that aligns with the CAD model v3 you forwarded last week.
- **Range:** the Bosch HXF90 induction range needs 50mm clearance on each side per the install guide (p. 4).
- **Tile:** the Marazzi stone-look spec you bookmarked is 600×600mm — you'll need ~14 m² for the back wall.

I've drafted a brief to send to your kitchen fitter summarising these dimensions and the cutout specs.

```action
{"type": "share_document", "summary": "Share kitchen brief with builder (cutout + clearance specs)", "payload": {"audience": "kitchen_fitter", "brief": "# Kitchen cutout + clearance brief\\n\\n- Sink cutout: 762mm × 457mm\\n- Range: Bosch HXF90 induction; 50mm side clearance required\\n- Tile: Marazzi 600×600 stone-look; ~14 m² for back wall\\n\\nSourced from Bosch sink spec (p.2), Bosch range install guide (p.4), Marazzi product card."}, "confidence": 0.82}
```"""


_DEMO_APPOINTMENT = """Found two references to upcoming appointments in the recent letters:

- **Cardiology follow-up** mentioned in Dr. Hartley's letter dated 14 Mar 2026 — likely the one referenced for early April.
- **Repeat bloods** requested by the practice nurse at the last visit.

I can queue the cardiology date as a calendar event once you confirm — I don't want to invent the exact day.

```action
{"type": "create_calendar_event", "summary": "Cardiology follow-up — Dr. Hartley (date TBC)", "payload": {"title": "Cardiology follow-up — Dr. Hartley", "start": "2026-04-08T10:00:00Z", "end": "2026-04-08T10:30:00Z", "location": "Royal London Hospital"}, "confidence": 0.74}
```"""


_DEMO_HUSBAND = """Based on the timeline I've seen across his medical letters:

- **2025-11 to 2026-03:** 3 admissions, mostly for symptom monitoring rather than acute intervention.
- **Medication:** current regimen referenced in the 14 Mar letter from Dr. Hartley.
- **Pattern flag:** the symptom progression notes from 04 Feb and 18 Mar both mention increased fatigue — possibly worth raising at the next consultation.

I can prepare a one-page brief for the next appointment if you'd like.

```action
{"type": "appointment_brief", "summary": "Draft appointment brief for next cardiology visit", "payload": {"clinician": "Dr. Hartley", "appointment_date": "2026-04-08", "brief": "# Appointment brief — Dr. Hartley\\n\\n## Timeline summary\\n- 3 admissions Nov 2025 – Mar 2026\\n- Recurrent fatigue flagged in 2 recent letters\\n\\n## Questions to raise\\n- Progression of fatigue pattern\\n- Current medication review\\n- Any further investigations warranted?\\n\\n## Documents to bring\\n- 14 Mar letter (Dr. Hartley)\\n- 18 Mar symptom progression notes"}, "confidence": 0.81}
```"""


_DEMO_AGENT = """Sure — let's set up a new agent. To draft it I need a few quick details:

1. What's this project about? (one or two sentences)
2. What documents will go in?
3. What kinds of questions should it answer?
4. Anything it should never do?
5. Anything it should auto-run?

You can answer these one at a time and I'll build the spec as we go. (This is the AgentBuilder meta-agent in action — it creates new sub-agents on demand.)"""


_DEMO_DIGEST = """This week's digest (demo data):

**Remodel**
- 2 new product datasheets indexed (Bosch range, Marazzi tile)
- Vendor quote received from K&K Kitchens

**Husband's health**
- 1 new medical letter (Dr. Hartley, 14 Mar)
- No new admissions

**Your health**
- Nothing new this week

```action
{"type": "weekly_digest", "summary": "Compile weekly digest for Remodel project", "payload": {"project_id": "remodel"}, "confidence": 0.9}
```"""


_DEMO_DEFAULT = """I can help with that. I have access to your project documents, medical letters, and prior conversations. Try asking about:

- "What's the latest from the kitchen project?"
- "When is the next cardiology appointment?"
- "Compare the two contractor quotes for the bathroom"
- "Create a new agent for tracking the garden build"

Or just speak — the mic button is the easiest way. Note: this is **demo mode** — responses are canned. Set `TRG_DEMO_MODE=false` and a real `ANTHROPIC_API_KEY` in `.env` for live Claude calls.

```action
{"type": "create_calendar_event", "summary": "Demo: schedule a 5-min catch-up", "payload": {"title": "TRG catch-up", "start": "2026-09-02T15:00:00Z", "end": "2026-09-02T15:05:00Z", "location": ""}, "confidence": 0.6}
```"""
