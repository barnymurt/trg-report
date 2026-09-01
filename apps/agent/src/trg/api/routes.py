"""FastAPI routes for the agent backend."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from trg.audit.db import AuditDB
from trg.config.settings import Settings, get_settings
from trg.executor.executor import ActionExecutor
from trg.importers.claude import ClaudeImporter
from trg.orchestrator.agent_builder import AgentBuilder
from trg.orchestrator.manager import LifeCoordinator, ProposedAction
from trg.orchestrator.registry import AgentRegistry
from trg.rag.ingest import IngestionPipeline
from trg.stt.whisper_client import WhisperClient
from trg.tts.kokoro_client import KokoroClient


router = APIRouter()


# ─── Request / response models ──────────────────────────────────────────

class ChatRequest(BaseModel):
    project_id: str
    message: str
    audio_base64: str | None = None
    reply_with_audio: bool = False
    agent_id: str | None = None
    conversation_history: list[dict[str, str]] | None = None


class ChatResponse(BaseModel):
    response_text: str
    cited_chunks: list[dict[str, Any]]
    faithfulness_score: float
    proposed_actions: list[dict[str, Any]]
    tier_used: str
    cost_usd: float
    agent_id: str
    audio_base64: str | None = None


class TranscribeRequest(BaseModel):
    audio_base64: str
    language: str = "en"


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_sec: float


class BuilderRequest(BaseModel):
    user_message: str
    history: list[dict[str, str]] | None = None


class BuilderResponse(BaseModel):
    assistant_message: str
    draft_spec: dict[str, Any] | None
    ready_to_create: bool


class CreateAgentRequest(BaseModel):
    spec: dict[str, Any]


# ─── Dependencies ──────────────────────────────────────────────────────

def get_coordinator(request: Request) -> LifeCoordinator:
    return request.app.state.coordinator


def get_builder(request: Request) -> AgentBuilder:
    return request.app.state.agent_builder


def get_registry(request: Request) -> AgentRegistry:
    return request.app.state.registry


def get_settings_dep() -> Settings:
    return get_settings()


# ─── Health ─────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ─── Chat ───────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    coord: LifeCoordinator = Depends(get_coordinator),
    settings: Settings = Depends(get_settings_dep),
) -> ChatResponse:
    """Run a chat turn through the full RAG → Claude → verify pipeline."""
    # 1. If voice input, transcribe via Whisper first
    message_text = req.message
    if req.audio_base64:
        whisper = WhisperClient(settings)
        try:
            audio_bytes = base64.b64decode(req.audio_base64)
            transcription = await whisper.transcribe(audio_bytes)
            message_text = transcription.text or req.message
        finally:
            await whisper.close()

    # 2. Run the turn
    turn = await coord.chat(
        project_id=req.project_id,
        user_message=message_text,
        agent_id=req.agent_id,
        conversation_history=req.conversation_history,
    )

    # 3. Optional TTS reply
    audio_b64: str | None = None
    if req.reply_with_audio and turn.response_text:
        kokoro = KokoroClient(settings)
        try:
            wav = await kokoro.synthesise(turn.response_text)
            audio_b64 = base64.b64encode(wav).decode("ascii")
        finally:
            await kokoro.close()

    return ChatResponse(
        response_text=turn.response_text,
        cited_chunks=[
            {
                "id": c.id,
                "text": c.text,
                "score": c.score,
                "source": c.source,
                "page": c.page,
                "project_id": c.project_id,
            }
            for c in turn.cited_chunks
        ],
        faithfulness_score=turn.faithfulness_score,
        proposed_actions=[a.__dict__ for a in turn.proposed_actions],
        tier_used=turn.tier_used,
        cost_usd=turn.cost_usd,
        agent_id=turn.agent_id,
        audio_base64=audio_b64,
    )


# ─── Transcription (for real-time STT in the PWA) ─────────────────────

@router.post("/stt/transcribe", response_model=TranscribeResponse)
async def transcribe(
    req: TranscribeRequest,
    settings: Settings = Depends(get_settings_dep),
) -> TranscribeResponse:
    whisper = WhisperClient(settings)
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
        result = await whisper.transcribe(audio_bytes, language=req.language)
        return TranscribeResponse(
            text=result.text,
            language=result.language,
            duration_sec=result.duration_sec,
        )
    finally:
        await whisper.close()


# ─── TTS (synthesise reply audio on demand) ────────────────────────────

@router.post("/tts/synthesise")
async def synthesise(
    text: str,
    voice: str = "af_bella",
    speed: float = 1.0,
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    kokoro = KokoroClient(settings)
    try:
        wav = await kokoro.synthesise(text, voice=voice, speed=speed)
        return Response(content=wav, media_type="audio/wav")
    finally:
        await kokoro.close()


# ─── Agents ─────────────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents(
    registry: AgentRegistry = Depends(get_registry),
) -> list[dict[str, Any]]:
    return [a.to_dict() for a in registry.list()]


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_registry),
) -> dict[str, Any]:
    spec = registry.get(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return spec.to_dict()


# ─── AgentBuilder (meta-agent for creating new agents) ─────────────────

@router.post("/builder/chat", response_model=BuilderResponse)
async def builder_chat(
    req: BuilderRequest,
    builder: AgentBuilder = Depends(get_builder),
) -> BuilderResponse:
    turn = await builder.chat(req.user_message, req.history)
    return BuilderResponse(
        assistant_message=turn.assistant_message,
        draft_spec=turn.draft_spec,
        ready_to_create=turn.ready_to_create,
    )


@router.post("/builder/create")
async def builder_create(
    req: CreateAgentRequest,
    builder: AgentBuilder = Depends(get_builder),
) -> dict[str, Any]:
    spec = await builder.create_agent(req.spec)
    return spec.to_dict()


# ─── Document ingestion ────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_file(
    project_id: str,
    agent_id: str,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings_dep),
    registry: AgentRegistry = Depends(get_registry),
) -> dict[str, Any]:
    spec = registry.get(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="agent not found")
    # Save to document store
    safe_name = file.filename or "upload.bin"
    doc_path = settings.data_dir / "documents" / safe_name
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    with doc_path.open("wb") as f:
        f.write(await file.read())
    # Ingest
    pipeline = IngestionPipeline(settings)
    try:
        n = await pipeline.ingest_file(
            path=doc_path,
            project_id=project_id,
            collection=spec.qdrant_collection,
        )
    finally:
        await pipeline.close()
    return {"chunks_ingested": n, "filename": safe_name}


# ─── Audit ──────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit(
    project_id: str | None = None,
    days: int = 30,
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    audit = AuditDB(settings)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    claude_entries = audit.query(project_id=project_id, since=since, limit=500)
    event_entries = audit.query_events(project_id=project_id, since=since, limit=500)
    return {
        "claude_calls": claude_entries,
        "action_events": event_entries,
        "total_cost_usd": audit.total_cost_since(since),
        "period_days": days,
    }


@router.delete("/audit/project/{project_id}")
async def delete_project_audit(
    project_id: str,
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    audit = AuditDB(settings)
    deleted = audit.delete_project(project_id)
    return {"deleted_rows": deleted, "project_id": project_id}


# ─── Action execution ──────────────────────────────────────────────────

class ExecuteActionRequest(BaseModel):
    action_id: str
    project_id: str
    agent_id: str = ""
    action_type: str
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    cited_chunk_ids: list[str] = Field(default_factory=list)


class ExecuteActionResponse(BaseModel):
    ok: bool
    action_id: str
    action_type: str
    artefact_path: str | None
    error: str | None


@router.post("/actions/execute", response_model=ExecuteActionResponse)
async def execute_action(
    req: ExecuteActionRequest,
    settings: Settings = Depends(get_settings_dep),
) -> ExecuteActionResponse:
    executor = ActionExecutor(settings)
    proposed = ProposedAction(
        id=req.action_id,
        agent_id=req.agent_id,
        project_id=req.project_id,
        action_type=req.action_type,
        summary=req.summary,
        payload=req.payload,
        confidence=req.confidence,
        cited_chunk_ids=req.cited_chunk_ids,
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    )
    result = await executor.execute(proposed)
    return ExecuteActionResponse(
        ok=result.ok,
        action_id=result.action_id,
        action_type=result.action_type,
        artefact_path=result.artefact_path,
        error=result.error,
    )


class ExecuteBatchRequest(BaseModel):
    actions: list[ExecuteActionRequest]


class ExecuteBatchResponse(BaseModel):
    results: list[ExecuteActionResponse]


@router.post("/actions/execute-batch", response_model=ExecuteBatchResponse)
async def execute_batch(
    req: ExecuteBatchRequest,
    settings: Settings = Depends(get_settings_dep),
) -> ExecuteBatchResponse:
    executor = ActionExecutor(settings)
    proposed_list = [
        ProposedAction(
            id=a.action_id,
            agent_id=a.agent_id,
            project_id=a.project_id,
            action_type=a.action_type,
            summary=a.summary,
            payload=a.payload,
            confidence=a.confidence,
            cited_chunk_ids=a.cited_chunk_ids,
            created_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        )
        for a in req.actions
    ]
    results = await executor.execute_batch(proposed_list)
    return ExecuteBatchResponse(
        results=[
            ExecuteActionResponse(
                ok=r.ok,
                action_id=r.action_id,
                action_type=r.action_type,
                artefact_path=r.artefact_path,
                error=r.error,
            )
            for r in results
        ]
    )


# ─── Importers ─────────────────────────────────────────────────────────

class ImportClaudeRequest(BaseModel):
    path: str = Field(..., description="Absolute path to ZIP file or extracted directory.")
    default_project: str = "general"


class ImportClaudeResponse(BaseModel):
    conversations_seen: int
    chunks_imported: int
    by_project: dict[str, int]
    errors: list[str]


@router.post("/import/claude", response_model=ImportClaudeResponse)
async def import_claude(
    req: ImportClaudeRequest,
    settings: Settings = Depends(get_settings_dep),
) -> ImportClaudeResponse:
    importer = ClaudeImporter(settings)
    try:
        report = await importer.import_path(
            req.path, default_project=req.default_project
        )
    finally:
        await importer.close()
    return ImportClaudeResponse(
        conversations_seen=report.conversations_seen,
        chunks_imported=report.chunks_imported,
        by_project=report.by_project,
        errors=report.errors,
    )
