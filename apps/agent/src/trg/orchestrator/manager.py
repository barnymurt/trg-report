"""LifeCoordinator — the manager agent that routes user input to the right
sub-agent, compresses context, and assembles the final response.

Built on smolagents' MultiStepAgent hierarchy. Per-agent model selection
keeps Claude token cost low.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from trg.audit.db import AuditDB, AuditEntry
from trg.config.settings import Settings, get_settings
from trg.llm.claude import ClaudeClient
from trg.llm.smollm2 import SmolLM2Client
from trg.orchestrator.registry import AgentRegistry, AgentSpec
from trg.rag.faithfulness import FaithfulnessScorer
from trg.rag.retriever import RetrievedChunk, Retriever


@dataclass
class ProposedAction:
    """A proposed action that needs human approval."""

    id: str
    agent_id: str
    project_id: str
    action_type: str
    summary: str
    payload: dict[str, Any]
    confidence: float
    cited_chunk_ids: list[str]
    created_at: str
    status: str = "pending"  # pending | approved | rejected | edited | executed
    whitelisted: bool = False


@dataclass
class ChatTurn:
    """Result of a single chat turn."""

    response_text: str
    cited_chunks: list[RetrievedChunk]
    faithfulness_score: float
    proposed_actions: list[ProposedAction]
    tier_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    agent_id: str


class LifeCoordinator:
    """The orchestrator. Routes, retrieves, compresses, reasons, verifies."""

    def __init__(
        self,
        settings: Settings | None = None,
        registry: AgentRegistry | None = None,
        claude: ClaudeClient | None = None,
        smollm2: SmolLM2Client | None = None,
        retriever: Retriever | None = None,
        faithfulness: FaithfulnessScorer | None = None,
        audit: AuditDB | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or AgentRegistry(self.settings)
        self.claude = claude or ClaudeClient(self.settings)
        self.smollm2 = smollm2 or SmolLM2Client(self.settings)
        self.retriever = retriever or Retriever(self.settings)
        self.faithfulness = faithfulness or FaithfulnessScorer(self.settings)
        self.audit = audit or AuditDB(self.settings)

    async def chat(
        self,
        *,
        project_id: str,
        user_message: str,
        agent_id: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        reply_with_audio: bool = False,
    ) -> ChatTurn:
        """Run a chat turn through the full pipeline."""
        # 1. Pick the right agent
        agent = self._resolve_agent(project_id, agent_id)
        if agent is None:
            raise ValueError(
                f"No agent found for project_id={project_id} agent_id={agent_id}"
            )

        # 2. Retrieve relevant evidence from the project's Qdrant collection
        chunks: list = []
        if not self.settings.trg_demo_mode:
            try:
                chunks = await self.retriever.retrieve(
                    query=user_message,
                    collection=agent.qdrant_collection,
                    project_id=project_id,
                )
            except Exception as e:  # noqa: BLE001
                # Local services may be down — degrade gracefully
                import logging
                logging.getLogger(__name__).warning(
                    "retrieval failed (services down?): %s", e
                )
                chunks = []

        # 3. Classify difficulty → pick Claude tier
        difficulty = "medium"
        if not self.settings.trg_demo_mode:
            try:
                difficulty = await self.smollm2.classify_difficulty(user_message)
            except Exception:
                difficulty = "medium"
        tier = agent.model_tiers.get(difficulty, "haiku")

        # 4. Compress retrieved context to fit budget (using SmolLM2 if many chunks)
        evidence_text = ""
        if chunks and len(chunks) >= 3 and not self.settings.trg_demo_mode:
            try:
                evidence_text = await self.smollm2.compress(
                    [c.text for c in chunks],
                    target_tokens=self.settings.compression_target_tokens,
                    query=user_message,
                )
            except Exception:
                evidence_text = "\n\n".join(c.text for c in chunks)
        else:
            evidence_text = "\n\n".join(c.text for c in chunks)

        # 5. Build the system prompt with the agent's role + evidence
        system_prompt = (
            f"{agent.system_prompt}\n\n"
            f"You are responding within the project '{project_id}'. "
            f"When you reference evidence, cite it as [chunk-N] using the "
            f"numbered list below. If evidence is insufficient, say so plainly.\n\n"
            f"Evidence:\n"
            + "\n".join(
                f"[chunk-{i}] {c.text}\n(source: {c.source}, page: {c.page or 'n/a'})"
                for i, c in enumerate(chunks)
            )
        )

        messages: list[dict[str, str]] = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        # 6. Call Claude (or demo stub)
        response_text, call = await self.claude.complete(
            tier=tier,
            system=system_prompt,
            messages=messages,
            project_id=project_id,
            agent_id=agent.id,
            retrieved_chunk_ids=[c.id for c in chunks],
            extended_thinking=(tier == "sonnet-thinking"),
        )

        # 7. Faithfulness check (skip in demo mode)
        faithfulness_score = 1.0
        if not self.settings.trg_demo_mode:
            try:
                faithfulness_score = await self.faithfulness.score(
                    response=response_text,
                    evidence_chunks=[c.text for c in chunks] if chunks else [],
                )
            except Exception:
                faithfulness_score = 0.5

        # 8. Extract any proposed actions from the response
        proposed = self._extract_proposed_actions(
            response_text=response_text,
            agent_id=agent.id,
            project_id=project_id,
            cited_chunks=chunks,
        )

        # 9. Audit log
        self.audit.write(
            AuditEntry(
                project_id=project_id,
                agent_id=agent.id,
                tier=tier,
                prompt_hash=call.prompt_hash,
                prompt_summary=user_message[:200],
                retrieved_chunk_ids=[c.id for c in chunks],
                response_text=response_text,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
                faithfulness_score=faithfulness_score,
            )
        )

        return ChatTurn(
            response_text=response_text,
            cited_chunks=chunks,
            faithfulness_score=faithfulness_score,
            proposed_actions=proposed,
            tier_used=tier,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            cost_usd=call.cost_usd,
            agent_id=agent.id,
        )

    def _resolve_agent(self, project_id: str, agent_id: str | None) -> AgentSpec | None:
        if agent_id:
            return self.registry.get(agent_id)
        # Pick first agent whose description matches the project_id (simple heuristic)
        for agent in self.registry.list():
            if project_id in agent.name.lower() or project_id in agent.id.lower():
                return agent
        # Fall back: first agent
        agents = self.registry.list()
        return agents[0] if agents else None

    def _extract_proposed_actions(
        self,
        *,
        response_text: str,
        agent_id: str,
        project_id: str,
        cited_chunks: list[RetrievedChunk],
    ) -> list[ProposedAction]:
        """Look for a JSON block of the form:

        ```action
        {"type": "...", "summary": "...", "payload": {...}}
        ```
        """
        actions: list[ProposedAction] = []
        marker = "```action"
        idx = response_text.find(marker)
        while idx != -1:
            end = response_text.find("```", idx + len(marker))
            if end == -1:
                break
            block = response_text[idx + len(marker) : end].strip()
            try:
                data = json.loads(block)
                actions.append(
                    ProposedAction(
                        id=str(uuid.uuid4()),
                        agent_id=agent_id,
                        project_id=project_id,
                        action_type=data.get("type", "custom"),
                        summary=data.get("summary", ""),
                        payload=data.get("payload", {}),
                        confidence=float(data.get("confidence", 0.7)),
                        cited_chunk_ids=[c.id for c in cited_chunks],
                        created_at=__import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat(),
                    )
                )
            except Exception:
                pass
            idx = response_text.find(marker, end)
        return actions

    async def close(self) -> None:
        await self.claude._client.close()  # type: ignore[attr-defined]
        await self.smollm2.close()
        await self.retriever.close()
        await self.faithfulness.close()
