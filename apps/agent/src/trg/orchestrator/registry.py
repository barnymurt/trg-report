"""Agent registry — persists agent specs to disk.

Each agent is a JSON spec saved under `data/config/agents/`. The registry
loads them at startup and exposes a typed lookup. New agents created via
AgentBuilder are written here.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trg.config.settings import Settings, get_settings


class AgentSpec:
    """Runtime representation of an agent."""

    def __init__(
        self,
        *,
        id: str,
        name: str,
        description: str,
        system_prompt: str,
        qdrant_collection: str,
        tools: list[str],
        model_tiers: dict[str, str],
        starter_whitelist: list[dict[str, Any]] | None = None,
        starter_blacklist: list[dict[str, Any]] | None = None,
        parent_agent_id: str | None = None,
        created_at: str | None = None,
        created_by: str = "human",
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.qdrant_collection = qdrant_collection
        self.tools = tools
        self.model_tiers = model_tiers
        self.starter_whitelist = starter_whitelist or []
        self.starter_blacklist = starter_blacklist or []
        self.parent_agent_id = parent_agent_id
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.created_by = created_by

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSpec":
        return cls(**data)


class AgentRegistry:
    """File-backed agent registry."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.agents_dir = self.settings.config_dir / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[AgentSpec]:
        return [self._load(p) for p in sorted(self.agents_dir.glob("*.json"))]

    def get(self, agent_id: str) -> AgentSpec | None:
        path = self.agents_dir / f"{agent_id}.json"
        if not path.exists():
            return None
        return self._load(path)

    def upsert(self, spec: AgentSpec) -> None:
        path = self.agents_dir / f"{spec.id}.json"
        path.write_text(
            json.dumps(spec.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, agent_id: str) -> bool:
        path = self.agents_dir / f"{agent_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def _load(self, path: Path) -> AgentSpec:
        return AgentSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))


def new_agent_id() -> str:
    return uuid.uuid4().hex[:12]
