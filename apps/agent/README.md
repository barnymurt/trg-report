# TRG Agent Backend

Python backend for the TRG multi-agent Claude system. Built on FastAPI + smolagents.

## Components

| Module | Purpose |
|---|---|
| `trg.llm.claude` | Anthropic SDK wrapper with cost + audit hooks |
| `trg.llm.smollm2` | Local LLM client (routing, compression, trivial Q&A) |
| `trg.llm.tokens` | Claude cost estimation |
| `trg.rag.retriever` | Embed → Qdrant → rerank |
| `trg.rag.ingest` | Document ingestion via Docling |
| `trg.rag.faithfulness` | NLI-based faithfulness scoring |
| `trg.stt.whisper_client` | STT via faster-whisper |
| `trg.tts.kokoro_client` | TTS via Kokoro-82M |
| `trg.audit.db` | SQLite audit log |
| `trg.orchestrator.registry` | Agent spec persistence |
| `trg.orchestrator.manager` | LifeCoordinator (the main pipeline) |
| `trg.orchestrator.agent_builder` | AgentBuilder (meta-agent) |
| `trg.agents.seeds` | Default seed agents |
| `trg.tools.smolagents_tools` | Tools exposed to sub-agents |
| `trg.api.routes` | FastAPI routes |
| `trg.main` | Application entry |

## Pipeline

```
user message
    ↓
[optional STT via Whisper]
    ↓
SmolLM2: classify project + classify difficulty
    ↓
Qdrant: retrieve top-20 from project collection
    ↓
TEI reranker: rerank to top-5
    ↓
SmolLM2: compress evidence to ~3k tokens
    ↓
Claude (Haiku / Sonnet / Sonnet+thinking) — tier chosen by difficulty
    ↓
NLI faithfulness check
    ↓
Extract any ```action``` blocks → ProposedAction objects
    ↓
Audit log entry
    ↓
[optional TTS via Kokoro]
    ↓
response to PWA
```

## Running locally

```bash
cd apps/agent
pip install -e .
uvicorn trg.main:app --reload --port 8000
```

Or via Docker Compose from the repo root:

```bash
pnpm infra:up
```

## API surface

See `src/trg/api/routes.py` for the full set. Highlights:

- `POST /chat` — full pipeline, accepts voice (base64) and returns optional TTS audio
- `POST /stt/transcribe` — Whisper-only transcription
- `POST /tts/synthesise` — Kokoro TTS
- `GET /agents` — list all agents
- `POST /builder/chat` — guided conversation with AgentBuilder
- `POST /builder/create` — materialise a new agent from a draft spec
- `POST /ingest` — upload a PDF/image/text to a project's collection
- `GET /audit` — query the audit log ("show me everything sent to Anthropic")
- `DELETE /audit/project/{project_id}` — right-to-delete
