"""AgentBuilder — meta-agent that creates new sub-agents on demand.

When the user opens the "Create new agent" UI flow, she chats with
AgentBuilder. AgentBuilder asks clarifying questions, drafts an AgentSpec,
and (after her approval) creates the Qdrant collection + writes the spec
into the registry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from trg.audit.db import AuditDB
from trg.config.settings import Settings, get_settings
from trg.llm.claude import ClaudeClient
from trg.llm.smollm2 import SmolLM2Client
from trg.orchestrator.manager import LifeCoordinator
from trg.orchestrator.registry import AgentRegistry, AgentSpec, new_agent_id
from trg.rag.retriever import Retriever


@dataclass
class BuilderTurn:
    """A single turn in the AgentBuilder conversation."""

    assistant_message: str
    draft_spec: dict | None  # populated when AgentBuilder has enough info
    ready_to_create: bool


CLARIFYING_QUESTIONS = [
    "What's this project about? (one or two sentences)",
    "What kinds of documents will go into it? (PDFs, images, plain notes)",
    "What kinds of questions should this agent answer?",
    "Anything it should NEVER do? (auto-blacklist)",
    "Anything it should auto-run by default? (whitelist)",
    "Does it have a parent agent? (e.g. a Cardiology sub-track of HusbandHealth)",
]


SYSTEM_PROMPT = """You are AgentBuilder — the meta-agent that creates new
sub-agents for the TRG system.

You talk to a non-technical user (a retired professor). She describes what
she needs in plain English. Your job:

  1. Ask the clarifying questions needed to define a useful agent
     (only the ones that genuinely matter; don't make her type more than
     necessary).
  2. Once you have enough, propose a complete AgentSpec as JSON wrapped in
     a fenced block:

        ```spec
        {
          "name": "...",
          "description": "...",
          "system_prompt": "...",
          "qdrant_collection": "...",
          "tools": [...],
          "model_tiers": {"trivial": "smollm2", "medium": "haiku", "hard": "sonnet", "expert": "sonnet-thinking"},
          "starter_whitelist": [...],
          "starter_blacklist": [...],
          "parent_agent_id": null
        }
        ```

  3. After the user approves, the orchestrator calls create_agent() with
     the spec. The new agent immediately appears in the project list.

Be brief, friendly, and never condescending. She is highly intelligent;
she just doesn't want to type a lot.
"""


class AgentBuilder:
    """The meta-agent that creates new agents."""

    def __init__(
        self,
        settings: Settings | None = None,
        registry: AgentRegistry | None = None,
        claude: ClaudeClient | None = None,
        coordinator: LifeCoordinator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or AgentRegistry(self.settings)
        self.claude = claude or ClaudeClient(self.settings)
        self.coordinator = coordinator or LifeCoordinator(self.settings)

    async def start(self) -> str:
        """Open the conversation. Returns the opening message."""
        return (
            "Hi — I'll help you create a new agent. Tell me, in your own words, "
            "what do you want it to do? (You can also pick from a template: "
            "remodel-subproject, health-subtrack, research-topic, admin-coordination.)"
        )

    async def chat(
        self, user_message: str, history: list[dict[str, str]] | None = None
    ) -> BuilderTurn:
        """Process one turn in the AgentBuilder conversation."""
        messages: list[dict[str, str]] = list(history or [])
        messages.append({"role": "user", "content": user_message})

        response_text, _ = await self.claude.complete(
            tier="sonnet",  # meta-reasoning warrants Sonnet
            system=SYSTEM_PROMPT,
            messages=messages,
            project_id="agent-builder",
            agent_id="agent-builder",
        )

        spec = self._extract_spec(response_text)
        return BuilderTurn(
            assistant_message=response_text,
            draft_spec=spec,
            ready_to_create=spec is not None and "create now" in user_message.lower(),
        )

    def _extract_spec(self, text: str) -> dict | None:
        """Look for a ```spec ...``` JSON block in the response."""
        marker = "```spec"
        idx = text.find(marker)
        if idx == -1:
            return None
        end = text.find("```", idx + len(marker))
        if end == -1:
            return None
        block = text[idx + len(marker) : end].strip()
        try:
            return json.loads(block)
        except Exception:
            return None

    async def create_agent(self, spec: dict) -> AgentSpec:
        """Materialise a new agent from a draft spec.

        - Writes the spec into the registry
        - Creates the Qdrant collection
        """
        agent_id = spec.get("id") or new_agent_id()
        full_spec = AgentSpec(
            id=agent_id,
            name=spec["name"],
            description=spec.get("description", ""),
            system_prompt=spec.get("system_prompt", f"You are the {spec['name']} agent."),
            qdrant_collection=spec.get("qdrant_collection", f"project-{agent_id}"),
            tools=spec.get("tools", []),
            model_tiers=spec.get(
                "model_tiers",
                {
                    "trivial": "smollm2",
                    "medium": "haiku",
                    "hard": "sonnet",
                    "expert": "sonnet-thinking",
                },
            ),
            starter_whitelist=spec.get("starter_whitelist", []),
            starter_blacklist=spec.get("starter_blacklist", []),
            parent_agent_id=spec.get("parent_agent_id"),
            created_by="agent-builder",
        )
        self.registry.upsert(full_spec)
        await self.coordinator.retriever.ensure_collection(full_spec.qdrant_collection)
        return full_spec
