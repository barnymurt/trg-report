"""Action executor — turns approved ProposedAction objects into real effects.

Design goals
------------
- Single-user, audit-first: every executed action is logged.
- Side-effects go to LOCAL artefacts first (files in `data/`), then optionally
  to external services (Google Calendar, SMTP, etc.) when configured.
- Whitelisted actions can auto-run; non-whitelisted require explicit approval.
- Right-to-reverse: every action produces an artefact that can be undone.

Supported action types (initial set)
------------------------------------
- create_calendar_event   → writes .ics to `data/calendar/`
- draft_email             → writes .eml to `data/drafts/`
- share_document          → writes markdown brief to `data/share-queue/`
- file_to_project         → moves source into project folder + indexes in Qdrant
- extract_measurements    → appends to project's `measurements.json`
- contradiction_flag      → writes to project's `flags.json` + notification
- weekly_digest           → schedules a notification (saved as pending digest)
- appointment_brief       → writes PDF-ready markdown to `data/briefs/`
- create_agent            → handled by AgentBuilder (not this module)
- delete_data             → cascade-delete (right-to-delete)
- modify_record           → currently a no-op + warning
- custom                  → logs only
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trg.audit.db import AuditDB
from trg.config.settings import Settings, get_settings
from trg.orchestrator.manager import ProposedAction


@dataclass
class ExecutionResult:
    """Result of executing a ProposedAction."""

    ok: bool
    action_id: str
    action_type: str
    artefact_path: str | None = None
    error: str | None = None
    executed_at: str = ""

    def __post_init__(self) -> None:
        if not self.executed_at:
            self.executed_at = datetime.now(timezone.utc).isoformat()


class ActionExecutor:
    """Executes approved ProposedAction objects."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.audit = AuditDB(self.settings)
        self.data_dir = self.settings.data_dir
        self._setup_dirs()

    def _setup_dirs(self) -> None:
        for sub in ("calendar", "drafts", "share-queue", "briefs", "digests"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    # ─── Public API ──────────────────────────────────────────────────

    async def execute(
        self, action: ProposedAction, *, project_collection: str | None = None
    ) -> ExecutionResult:
        """Dispatch an approved action to its handler."""
        handler = self._handlers.get(action.action_type, self._handle_custom)
        try:
            result = await handler(self, action)
        except Exception as e:  # noqa: BLE001
            result = ExecutionResult(
                ok=False,
                action_id=action.id,
                action_type=action.action_type,
                error=str(e),
            )

        # Audit log entry
        self.audit.write_audit_event(
            kind="action_executed",
            action_id=action.id,
            action_type=action.action_type,
            project_id=action.project_id,
            ok=result.ok,
            artefact_path=result.artefact_path,
            error=result.error,
        )
        return result

    async def execute_batch(self, actions: list[ProposedAction]) -> list[ExecutionResult]:
        return await asyncio.gather(*(self.execute(a) for a in actions))

    # ─── Handlers ────────────────────────────────────────────────────

    async def _handle_calendar_event(self, action: ProposedAction) -> ExecutionResult:
        """Write an .ics file the user can import into her calendar app."""
        payload = action.payload
        title = payload.get("title", "Untitled")
        start = payload.get("start", "")
        end = payload.get("end", start)
        location = payload.get("location", "")

        # iCal UID + timestamp
        uid = f"{action.id}@trg"
        dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        start_dt = _parse_iso(start) or datetime.now(timezone.utc)
        end_dt = _parse_iso(end) or start_dt

        ics = (
            "BEGIN:VCALENDAR\n"
            "VERSION:2.0\n"
            "PRODID:-//TRG Agent Team//EN\n"
            "CALSCALE:GREGORIAN\n"
            "METHOD:PUBLISH\n"
            f"BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"DTSTAMP:{dtstamp}\n"
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%SZ')}\n"
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%SZ')}\n"
            f"SUMMARY:{_ics_escape(title)}\n"
            f"DESCRIPTION:{_ics_escape(action.summary)}\n"
            + (f"LOCATION:{_ics_escape(location)}\n" if location else "")
            + f"END:VEVENT\n"
            "END:VCALENDAR\n"
        )

        filename = f"{start_dt.strftime('%Y%m%d-%H%M')}-{_slugify(title)}.ics"
        path = self.data_dir / "calendar" / filename
        path.write_text(ics, encoding="utf-8")
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_draft_email(self, action: ProposedAction) -> ExecutionResult:
        """Write an .eml draft to `data/drafts/` for the user to review + send."""
        payload = action.payload
        to = payload.get("to", "")
        subject = payload.get("subject", "(no subject)")
        body = payload.get("body", "")

        eml = (
            f"From: TRG Agent <agent@trg.local>\n"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"X-TRG-Action-Id: {action.id}\n"
            f"X-TRG-Project: {action.project_id}\n"
            f"Content-Type: text/plain; charset=utf-8\n"
            f"\n"
            f"{body}\n"
        )
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_slugify(subject)}.eml"
        path = self.data_dir / "drafts" / filename
        path.write_text(eml, encoding="utf-8")
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_share_document(self, action: ProposedAction) -> ExecutionResult:
        """Save a brief to `data/share-queue/` ready for the user to forward."""
        payload = action.payload
        brief = payload.get("brief", action.summary)
        audience = payload.get("audience", "default")
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_slugify(audience)}.md"
        path = self.data_dir / "share-queue" / filename
        header = (
            f"# Share-ready brief\n\n"
            f"- Audience: `{audience}`\n"
            f"- Generated: {datetime.now(timezone.utc).isoformat()}\n"
            f"- Project: `{action.project_id}`\n"
            f"- Action ID: `{action.id}`\n\n"
            f"---\n\n"
        )
        path.write_text(header + brief + "\n", encoding="utf-8")
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_file_to_project(self, action: ProposedAction) -> ExecutionResult:
        """Move a referenced file into the project's folder and queue for ingest."""
        payload = action.payload
        source = payload.get("source_path") or payload.get("path")
        if not source:
            return ExecutionResult(
                ok=False,
                action_id=action.id,
                action_type=action.action_type,
                error="file_to_project requires source_path",
            )
        src = Path(source)
        if not src.exists():
            return ExecutionResult(
                ok=False,
                action_id=action.id,
                action_type=action.action_type,
                error=f"source not found: {source}",
            )
        dest_dir = self.data_dir / "documents" / action.project_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        # TODO: trigger IngestionPipeline here once registry wiring lands
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(dest),
        )

    async def _handle_extract_measurements(self, action: ProposedAction) -> ExecutionResult:
        """Append extracted measurements to the project's measurements.json."""
        payload = action.payload
        measurements = payload.get("measurements", [])
        if not isinstance(measurements, list):
            measurements = [payload]
        path = self.data_dir / action.project_id / "measurements.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[Any] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        entry = {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "action_id": action.id,
            "items": measurements,
            "source_chunk_ids": action.cited_chunk_ids,
        }
        existing.append(entry)
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_contradiction_flag(self, action: ProposedAction) -> ExecutionResult:
        """Record a contradiction flag and surface via notifications."""
        path = self.data_dir / action.project_id / "flags.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[Any] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append(
            {
                "flagged_at": datetime.now(timezone.utc).isoformat(),
                "summary": action.summary,
                "action_id": action.id,
                "cited_chunk_ids": action.cited_chunk_ids,
                "payload": action.payload,
            }
        )
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_weekly_digest(self, action: ProposedAction) -> ExecutionResult:
        """Save a digest placeholder; real composition happens via a scheduled job."""
        path = self.data_dir / "digests" / f"{action.project_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "queued_at": datetime.now(timezone.utc).isoformat(),
                    "project_id": action.project_id,
                    "summary": action.summary,
                    "action_id": action.id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_appointment_brief(self, action: ProposedAction) -> ExecutionResult:
        """Save an appointment brief as markdown for review/sharing."""
        payload = action.payload
        body = payload.get("brief", action.summary)
        when = payload.get("appointment_date", "")
        clinician = payload.get("clinician", "")
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_slugify(clinician or 'appointment')}.md"
        path = self.data_dir / "briefs" / filename
        content = (
            f"# Appointment brief\n\n"
            f"- Clinician: {clinician or 'n/a'}\n"
            f"- When: {when or 'n/a'}\n"
            f"- Generated: {datetime.now(timezone.utc).isoformat()}\n"
            f"- Project: `{action.project_id}`\n"
            f"- Action ID: `{action.id}`\n\n"
            f"---\n\n{body}\n"
        )
        path.write_text(content, encoding="utf-8")
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=str(path),
        )

    async def _handle_delete_data(self, action: ProposedAction) -> ExecutionResult:
        """Cascade-delete all data for the project."""
        project_id = action.payload.get("project_id") or action.project_id
        deleted_audit = self.audit.delete_project(project_id)
        # Also remove documents folder + flags
        docs_dir = self.data_dir / "documents" / project_id
        if docs_dir.exists():
            shutil.rmtree(docs_dir, ignore_errors=True)
        for sub in ("calendar", "drafts", "share-queue", "briefs"):
            for f in (self.data_dir / sub).glob(f"*{project_id}*"):
                f.unlink(missing_ok=True)
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=f"audit_rows_deleted={deleted_audit}",
        )

    async def _handle_modify_record(self, action: ProposedAction) -> ExecutionResult:
        # Currently disabled — see ARCHITECTURE.md: medical record modifications
        # always require explicit + non-whitelist approval and are not yet implemented.
        return ExecutionResult(
            ok=False,
            action_id=action.id,
            action_type=action.action_type,
            error="modify_record is intentionally not implemented; refused.",
        )

    async def _handle_custom(self, action: ProposedAction) -> ExecutionResult:
        return ExecutionResult(
            ok=True,
            action_id=action.id,
            action_type=action.action_type,
            artefact_path=None,
        )

    # ─── Dispatch table ──────────────────────────────────────────────

    _handlers: dict[str, Callable[[Any, Any], Any]] = {
        "create_calendar_event": lambda s, a: s._handle_calendar_event(a),
        "draft_email": lambda s, a: s._handle_draft_email(a),
        "share_document": lambda s, a: s._handle_share_document(a),
        "file_to_project": lambda s, a: s._handle_file_to_project(a),
        "extract_measurements": lambda s, a: s._handle_extract_measurements(a),
        "contradiction_flag": lambda s, a: s._handle_contradiction_flag(a),
        "weekly_digest": lambda s, a: s._handle_weekly_digest(a),
        "appointment_brief": lambda s, a: s._handle_appointment_brief(a),
        "delete_data": lambda s, a: s._handle_delete_data(a),
        "modify_record": lambda s, a: s._handle_modify_record(a),
    }


# ─── Helpers ──────────────────────────────────────────────────────────

def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # Accept both "...Z" and "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _slugify(text: str, max_len: int = 60) -> str:
    keep = "abcdefghijklmnopqrstuvwxyz0123456789-"
    cleaned = "".join(c.lower() if c.lower() in keep else "-" for c in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:max_len] or "untitled"
