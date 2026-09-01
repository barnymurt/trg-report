"""Seed agents — created on first boot if registry is empty.

Defines the initial team: Remodel, HusbandHealth, OwnHealth, Calendar,
Inbox, plus AgentBuilder.
"""

from __future__ import annotations

from trg.config.settings import Settings, get_settings
from trg.orchestrator.registry import AgentRegistry, AgentSpec, new_agent_id

DEFAULT_TIERS = {
    "trivial": "smollm2",
    "medium": "haiku",
    "hard": "sonnet",
    "expert": "sonnet-thinking",
}


SEED_AGENTS: list[AgentSpec] = [
    AgentSpec(
        id=new_agent_id(),
        name="Remodel",
        description="House remodel — products, measurements, vendor coordination, CAD/spec notes.",
        system_prompt=(
            "You are the Remodel agent. You help the user track every detail "
            "of an extensive house remodel: product selections, measurements, "
            "vendor quotes, CAD/spec notes, and building-team coordination. "
            "You always cite the source PDF/page. You never invent dimensions — "
            "if a measurement is missing, you flag it. When proposing actions, "
            "you wrap them in a ```action``` JSON block so the user can approve "
            "before anything is shared externally."
        ),
        qdrant_collection="project-remodel",
        tools=["ingest_document", "draft_email", "share_with_builder"],
        model_tiers=DEFAULT_TIERS,
        starter_whitelist=[
            {"pattern": "Extract product specs from a PDF datasheet", "action_type": "extract_measurements", "enabled": True},
            {"pattern": "Add a vendor to the shortlist from a quote email", "action_type": "file_to_project", "enabled": True},
        ],
        starter_blacklist=[
            {"pattern": "Send an email to a builder without explicit approval", "action_type": "draft_email", "enabled": False},
            {"pattern": "Share a CAD file externally without approval", "action_type": "share_document", "enabled": False},
        ],
    ),
    AgentSpec(
        id=new_agent_id(),
        name="HusbandHealth",
        description="Husband's health — medical records, symptom timeline, appointment prep.",
        system_prompt=(
            "You are the HusbandHealth agent. You hold the longitudinal record "
            "of the user's husband's health: admissions, symptoms, medications, "
            "consultations, lab results. You prepare concise appointment briefs "
            "that cite the source letter/date. You flag patterns (recurring "
            "symptoms, medication interactions) but never diagnose. You propose "
            "calendar actions (```action``` block) for any new appointment date "
            "extracted from a medical letter. Privacy is paramount — every action "
            "is auditable and reversible."
        ),
        qdrant_collection="project-husband-health",
        tools=["ingest_document", "create_calendar_event", "draft_appointment_brief"],
        model_tiers=DEFAULT_TIERS,
        starter_whitelist=[
            {"pattern": "Extract dates from a medical letter and propose a calendar event", "action_type": "create_calendar_event", "enabled": True},
            {"pattern": "Flag a contradiction between two medical letters", "action_type": "contradiction_flag", "enabled": True},
            {"pattern": "Compile a weekly digest of new entries", "action_type": "weekly_digest", "enabled": True},
        ],
        starter_blacklist=[
            {"pattern": "Send any medical information to a third party without approval", "action_type": "share_document", "enabled": False},
            {"pattern": "Modify or delete medical records", "action_type": "modify_record", "enabled": False},
        ],
    ),
    AgentSpec(
        id=new_agent_id(),
        name="OwnHealth",
        description="Own health — separate from husband's, documented independently.",
        system_prompt=(
            "You are the OwnHealth agent. You mirror the HusbandHealth agent's "
            "capabilities for the user herself. Same privacy posture, same "
            "appointment-prep workflow, same citation discipline. Your memory is "
            "fully separate from HusbandHealth."
        ),
        qdrant_collection="project-own-health",
        tools=["ingest_document", "create_calendar_event", "draft_appointment_brief"],
        model_tiers=DEFAULT_TIERS,
        starter_whitelist=[
            {"pattern": "Extract dates from a medical letter and propose a calendar event", "action_type": "create_calendar_event", "enabled": True},
        ],
        starter_blacklist=[
            {"pattern": "Send any medical information to a third party without approval", "action_type": "share_document", "enabled": False},
            {"pattern": "Modify or delete medical records", "action_type": "modify_record", "enabled": False},
        ],
    ),
    AgentSpec(
        id=new_agent_id(),
        name="Calendar",
        description="Cross-cutting calendar — appointments, deadlines, supplier visits, travel.",
        system_prompt=(
            "You are the Calendar agent. You have read-only access to all "
            "projects. You surface upcoming events, detect conflicts (e.g. a "
            "kitchen supplier visit the same day as a hospital appointment), "
            "and propose a brief daily/weekly view."
        ),
        qdrant_collection="project-calendar",
        tools=["create_calendar_event"],
        model_tiers=DEFAULT_TIERS,
        starter_whitelist=[],
        starter_blacklist=[
            {"pattern": "Modify or delete calendar events without approval", "action_type": "modify_record", "enabled": False},
        ],
    ),
    AgentSpec(
        id=new_agent_id(),
        name="Inbox",
        description="Forwarded emails / voice notes → tagged and filed into the right project.",
        system_prompt=(
            "You are the Inbox agent. You receive forwarded emails and voice "
            "notes and decide which project they belong to (using the project "
            "classifier). You tag and file them. You never read the contents "
            "of forwarded medical letters aloud — privacy default."
        ),
        qdrant_collection="project-inbox",
        tools=["classify_project", "file_to_project"],
        model_tiers=DEFAULT_TIERS,
        starter_whitelist=[
            {"pattern": "Auto-file a forwarded email/voice note into the right project", "action_type": "file_to_project", "enabled": True},
        ],
        starter_blacklist=[],
    ),
]


def seed_if_empty(registry: AgentRegistry | None = None) -> list[AgentSpec]:
    """Create seed agents if registry is empty. Returns the full list."""
    settings = get_settings()
    registry = registry or AgentRegistry(settings)
    if registry.list():
        return registry.list()
    for spec in SEED_AGENTS:
        registry.upsert(spec)
    return registry.list()
