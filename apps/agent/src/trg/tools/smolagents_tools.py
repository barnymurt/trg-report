"""Smolagents tools exposed to sub-agents.

Tools are the actions an agent can take. They're wired to the actual
implementations (calendar API, email draft, etc.) but emit ProposedAction
objects for human approval before execution.
"""

from __future__ import annotations

import json
from typing import Any

from smolagents import Tool

from trg.audit.db import AuditDB
from trg.orchestrator.manager import LifeCoordinator


class IngestDocumentTool(Tool):
    """Trigger document ingestion for the active project."""

    name = "ingest_document"
    description = (
        "Ingest a PDF, image, or text file into the current project's Qdrant "
        "collection. Use when the user uploads or forwards a document."
    )
    inputs = {
        "path": {"type": "string", "description": "Absolute path to the file on disk."},
        "project_id": {"type": "string", "description": "Target project ID."},
    }
    output_type = "string"

    def __init__(self, coordinator: LifeCoordinator) -> None:
        super().__init__()
        self.coordinator = coordinator

    def forward(self, path: str, project_id: str) -> str:  # type: ignore[override]
        from trg.rag.ingest import IngestionPipeline

        async def _run() -> int:
            ingest = IngestionPipeline()
            agent = self.coordinator.registry.list()[0]  # TODO: resolve by project
            try:
                return await ingest.ingest_file(
                    path=path,
                    project_id=project_id,
                    collection=agent.qdrant_collection,
                )
            finally:
                await ingest.close()

        import asyncio
        n = asyncio.run(_run())
        return json.dumps({"chunks_ingested": n, "status": "ok"})


class DraftEmailTool(Tool):
    """Draft an email (NEVER sends — proposes for approval)."""

    name = "draft_email"
    description = (
        "Draft an email to a third party. The draft is proposed as a "
        "ProposedAction for the user to approve before sending. This tool "
        "NEVER sends an email."
    )
    inputs = {
        "to": {"type": "string", "description": "Recipient email address."},
        "subject": {"type": "string", "description": "Email subject line."},
        "body": {"type": "string", "description": "Email body text."},
        "project_id": {"type": "string", "description": "Originating project."},
    }
    output_type = "string"

    def forward(self, to: str, subject: str, body: str, project_id: str) -> str:  # type: ignore[override]
        return json.dumps(
            {
                "status": "proposed",
                "action": {
                    "type": "draft_email",
                    "summary": f"Draft email to {to}: {subject}",
                    "payload": {"to": to, "subject": subject, "body": body},
                },
                "note": "This is a proposal; nothing has been sent.",
            }
        )


class ShareWithBuilderTool(Tool):
    """Prepare a brief to share with a builder — requires approval."""

    name = "share_with_builder"
    description = (
        "Prepare a brief (text + measurements) to share with the building "
        "team. The share is proposed as a ProposedAction for approval."
    )
    inputs = {
        "brief": {"type": "string", "description": "Markdown brief to share."},
        "project_id": {"type": "string", "description": "Originating project."},
    }
    output_type = "string"

    def forward(self, brief: str, project_id: str) -> str:  # type: ignore[override]
        return json.dumps(
            {
                "status": "proposed",
                "action": {
                    "type": "share_document",
                    "summary": "Share a brief with the building team",
                    "payload": {"brief": brief, "audience": "building_team"},
                },
            }
        )


class CreateCalendarEventTool(Tool):
    """Propose a calendar event (NEVER creates without approval)."""

    name = "create_calendar_event"
    description = (
        "Propose a new calendar event. The proposal is queued for the "
        "user's approval — nothing is written to the calendar until approved."
    )
    inputs = {
        "title": {"type": "string", "description": "Event title."},
        "start": {"type": "string", "description": "ISO 8601 start datetime."},
        "end": {"type": "string", "description": "ISO 8601 end datetime."},
        "location": {"type": "string", "description": "Location or video link.", "nullable": True},
        "project_id": {"type": "string", "description": "Originating project."},
    }
    output_type = "string"

    def forward(  # type: ignore[override]
        self, title: str, start: str, end: str, location: str, project_id: str
    ) -> str:
        return json.dumps(
            {
                "status": "proposed",
                "action": {
                    "type": "create_calendar_event",
                    "summary": f"{title} — {start}",
                    "payload": {
                        "title": title,
                        "start": start,
                        "end": end,
                        "location": location,
                    },
                },
            }
        )


def all_tools(coordinator: LifeCoordinator) -> list[Tool]:
    """Return the full tool set available to agents."""
    return [
        IngestDocumentTool(coordinator),
        DraftEmailTool(),
        ShareWithBuilderTool(),
        CreateCalendarEventTool(),
    ]
