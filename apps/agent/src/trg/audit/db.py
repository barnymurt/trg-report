"""Audit logging for every Claude call and user-facing action.

Stores entries in a local SQLite DB (`data/audit.db`). Exposed via the PWA
("Show me everything sent to Anthropic in the last N days").

Schema:
  - id (uuid)
  - timestamp (ISO 8601)
  - project_id
  - agent_id
  - tier (haiku | sonnet | sonnet-thinking | smollm2)
  - prompt_hash (sha256 of the prompt payload — never the plaintext)
  - prompt_summary (short one-liner of the user query)
  - retrieved_chunk_ids (JSON array)
  - response_text (full response)
  - input_tokens
  - output_tokens
  - cost_usd
  - faithfulness_score
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trg.config.settings import Settings, get_settings


@dataclass
class AuditEntry:
    """A single Claude API call."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    project_id: str = ""
    agent_id: str = ""
    tier: str = "haiku"
    prompt_hash: str = ""
    prompt_summary: str = ""
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    response_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    faithfulness_score: float | None = None


class AuditDB:
    """SQLite-backed audit log."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = Path(self.settings.audit_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    project_id TEXT,
                    agent_id TEXT,
                    tier TEXT,
                    prompt_hash TEXT,
                    prompt_summary TEXT,
                    retrieved_chunk_ids TEXT,
                    response_text TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_usd REAL,
                    faithfulness_score REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_project ON audit(project_id)"
            )

    def write(self, entry: AuditEntry) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO audit (
                    id, timestamp, project_id, agent_id, tier, prompt_hash,
                    prompt_summary, retrieved_chunk_ids, response_text,
                    input_tokens, output_tokens, cost_usd, faithfulness_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp,
                    entry.project_id,
                    entry.agent_id,
                    entry.tier,
                    entry.prompt_hash,
                    entry.prompt_summary,
                    json.dumps(entry.retrieved_chunk_ids),
                    entry.response_text,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.cost_usd,
                    entry.faithfulness_score,
                ),
            )

    # ─── Action execution audit (separate from Claude-call audit) ────

    def write_audit_event(
        self,
        *,
        kind: str,
        action_id: str,
        action_type: str,
        project_id: str = "",
        ok: bool = True,
        artefact_path: str | None = None,
        error: str | None = None,
    ) -> None:
        """Log a non-Claude action (executor events, deletes, etc.)."""
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    action_id TEXT,
                    action_type TEXT,
                    project_id TEXT,
                    ok INTEGER,
                    artefact_path TEXT,
                    error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_ts ON audit_events(timestamp)"
            )
            conn.execute(
                """
                INSERT INTO audit_events (
                    id, timestamp, kind, action_id, action_type,
                    project_id, ok, artefact_path, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    datetime.now(timezone.utc).isoformat(),
                    kind,
                    action_id,
                    action_type,
                    project_id,
                    int(ok),
                    artefact_path,
                    error,
                ),
            )

    def query(
        self,
        *,
        project_id: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit WHERE 1=1"
        params: list[Any] = []
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                d["retrieved_chunk_ids"] = json.loads(d.get("retrieved_chunk_ids") or "[]")
                result.append(d)
            return result

    def query_events(
        self,
        *,
        project_id: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the audit_events table (action executions, deletes, etc.)."""
        sql = "SELECT * FROM audit_events WHERE 1=1"
        params: list[Any] = []
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def delete_project(self, project_id: str) -> int:
        """Right-to-delete: remove all entries for a project."""
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute("DELETE FROM audit WHERE project_id = ?", (project_id,))
            return cursor.rowcount

    def total_cost_since(self, since: str) -> float:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM audit WHERE timestamp >= ?",
                (since,),
            ).fetchone()
            return float(row[0]) if row else 0.0
