# TRG Agent Team — Architecture

> Multi-agent Claude system with RAG, voice input/output, and project isolation. Designed for a single mobile-first user (a retired public-health professor) running several concurrent life-projects: house remodel, husband's health, own health, plus on-demand sub-projects created via an **AgentBuilder** meta-agent.

---

## 1. The user

| Fact | Design implication |
|---|---|
| Mobile + voice-to-text is her primary surface | UI is a PWA styled like Claude mobile; STT is a first-class input |
| Typing tires her | Voice for input, TTS for replies (toggle) |
| Retired professor, public health + biobank data ethics | Privacy is a feature; audit logs + right-to-delete visible |
| Existing Claude Projects + Chat user | Match her existing mental model (projects, chat, context) |
| Three concurrent life domains | Each is its own project with isolated memory + collection |
| CAD + 3D + measurements matter | Document pipeline focused on PDFs + images + structured data |
| Husband's medical history is sensitive, evolving | Time-aware retrieval, appointment prep workflows |
| Wants automation **with final approval** | Agents emit `ProposedAction` objects; swipe-approve |
| Zero patience for AI slop | RAG with citations, confidence scores, faithfulness NLI |
| Often between meetings / traveling | Quick actions, low-friction, offline-tolerant |

---

## 2. Architecture (3 layers)

### Layer A — Mobile PWA

Installable web app. Single chat thread as primary surface, project tabs above.

- **Voice input** — `@ricky0123/vad-web` for VAD; MediaRecorder for capture; `distil-whisper/distil-large-v3` via faster-whisper for transcription
- **Optional TTS replies** — `hexgrad/Kokoro-82M` via HTTP
- **Project tabs** — Remodel · Husband's Health · My Health · Calendar · Inbox
- **Pending Actions tray** — swipe approve / edit / reject
- **Quick-action chips** per project
- **Audit Log view** — "show me everything sent to Anthropic in the last N days"
- **Settings** — TTS toggle, model tier overrides, whitelist management, data export/delete
- **Offline queue** — actions queue locally when offline; sync when reachable

### Layer B — Agent team (smolagents)

```
LifeCoordinator (manager) — SmolLM2 routes, Sonnet synthesises
├── RemodelAgent          (kitchen specs, measurements, vendor comms)
├── HusbandHealthAgent    (medical records, symptom timeline, appointment briefs)
├── OwnHealthAgent        (her own record, parallel)
├── CalendarAgent         (cross-cutting appointments / deadlines)
├── InboxAgent            (forwards into right project)
└── AgentBuilder          (meta-agent — creates new sub-agents on demand)
```

Each sub-agent:
- Owns a **Qdrant collection** (project isolation)
- Owns smolagents `agent.memory` (short-term scratchpad)
- Has a system prompt + tool allow-list
- Emits `ProposedAction` objects — never executes directly
- Selects tier per task: SmolLM2 → Haiku → Sonnet → Sonnet+thinking

**AgentBuilder** (meta-agent):
- Triggered from the PWA "Create new agent" menu
- Asks clarifying questions via Claude Sonnet
- Synthesises an `AgentSpec`
- On approval: creates Qdrant collection, writes spec to registry, agent appears immediately
- Pre-seeded templates: `remodel-subproject`, `health-subtrack`, `research-topic`, `admin-coordination`

### Layer C — RAG + memory infrastructure

| Component | Pick | Where |
|---|---|---|
| Vector DB | Qdrant | Local (Docker) |
| Embeddings (EN) | `BAAI/bge-small-en-v1.5` via TEI | Local |
| Embeddings (multilingual/long) | `BAAI/bge-m3` via TEI | Local |
| Reranker | `BAAI/bge-reranker-v2-m3` | Local |
| Project classifier | `sentence-transformers/all-MiniLM-L6-v2` | Local |
| STT | `distil-whisper/distil-large-v3` via faster-whisper | Local |
| TTS | `hexgrad/Kokoro-82M` | Local |
| Routing / compression LLM | `HuggingFaceTB/SmolLM2-1.7B-Instruct` (Q4) | Local |
| Reasoning LLM | Claude (Anthropic API) | Cloud |
| Doc ingestion | `ibm-granite/granite-docling-258M` + docling | Local |
| Faithfulness NLI | `MoritzLaurer/DeBERTa-v3-large-mnli-*` | Local |
| Audit | SQLite | Local |

---

## 3. Chat pipeline

```
user message
    ↓
[optional STT via Whisper]
    ↓
SmolLM2: classify project + classify difficulty
    ↓
Qdrant: retrieve top-20 from project collection (filtered by project_id)
    ↓
TEI reranker: rerank to top-5
    ↓
SmolLM2: compress evidence to ~3k tokens (if ≥3 chunks)
    ↓
Claude (Haiku / Sonnet / Sonnet+thinking) — tier chosen by difficulty
    ↓
NLI faithfulness check (DeBERTa-v3-large-mnli)
    ↓
Extract any ```action``` blocks → ProposedAction objects
    ↓
Audit log entry (project_id, agent_id, tier, prompt_hash, response_text, cost)
    ↓
[optional TTS via Kokoro]
    ↓
response to PWA
```

---

## 4. Privacy and data governance

### Posture
- All embeddings / STT / TTS / routing LLM / document parsing run on local hardware.
- Only the LLM reasoning calls hit Anthropic's API (separate billing from Claude.ai subscription).
- She has a biobank-ethics background — audit logs and right-to-delete are first-class features.

### What lives where
| Data | Location |
|---|---|
| Vector embeddings | Local Qdrant (per-project collections) |
| Document chunks | Local Qdrant payload + original file in `data/documents/` |
| Original PDFs/images | `data/documents/` (encrypted at rest via OS) |
| Audit log | Local SQLite (`data/audit.db`) |
| Backups | Encrypted nightly → `backups/` then synced to her existing iCloud/OneDrive |
| Claude requests | Sent to Anthropic API; only the system prompt + user message + compressed evidence |

### Audit log contents (per Claude call)
- `id`, `timestamp`, `project_id`, `agent_id`, `tier`
- `prompt_hash` (sha256 — for chain-of-custody)
- `prompt_summary` (first 200 chars of the user query, for human review)
- `retrieved_chunk_ids` (which evidence was used)
- `response_text` (full response)
- `input_tokens`, `output_tokens`, `cost_usd`
- `faithfulness_score`

### Right-to-delete
- PWA button → `DELETE /audit/project/{project_id}` cascades to all audit entries for that project
- Future: cascade-delete from Qdrant + document store as well

### Remote access (mobile)
- Cloudflare Tunnel (free) exposes the local agent backend to the internet over HTTPS
- No port forwarding required
- Tunnel terminates at Cloudflare; her home IP is never exposed
- The laptop must stay awake on AC power (`infra/scripts/setup-power.sh` configures this)

---

## 5. Cost discipline

1. **Voice-to-text** is local (faster-whisper) — free per call
2. **Embeddings** always local (TEI) — free per call
3. **SmolLM2** handles: project classification, retrieval, summarisation, compression, formatting, simple Q&A — **zero Claude tokens**
4. **Reranker** runs only when retrieval returns ≥20 candidates (configurable)
5. **Compression to ≤ 3k tokens** before any Claude call
6. **Tier auto-selection** by difficulty: `trivial → SmolLM2`, `medium → Haiku`, `hard → Sonnet`, `expert → Sonnet+thinking`
7. **Per-project monthly budget caps** (configurable; over-quota → fall back to local models)
8. **Faithfulness NLI** flags low-confidence answers; auto-retry on higher tier
9. **Audit log** surfaces token spend per project, per day

### Estimated monthly cost
- VPS / local hardware: $0 (runs on her existing computer)
- Anthropic API: a few $/month with Haiku-heavy use (~$0.25/MTok input)
- Cloudflare Tunnel: free
- Hugging Face Pro (optional for 24/7 backup): $2/mo — not needed for v1

---

## 6. Approval workflow ("final approval")

### Default behaviour
- **Nothing executes without explicit user approval**, except whitelisted safe actions.

### Whitelisted from day one (auto-run)
- Extract dates from a medical letter → calendar event with preview notification
- Tag and file a forwarded email/voice note into the correct project
- Compile a weekly per-project digest (Sunday 18:00 push)
- Detect a contradiction between two of her docs → surface flag
- Extract measurements from a product PDF → append to remodel shortlist
- Generate appointment brief → land in Pending Actions for approval before "send"

### Always requires approval
- Send any email externally
- Share any document externally
- Any financial action
- Modify any record
- Delete anything
- Any call outside the standard plan

### The flow
1. Agent decides to act.
2. Agent emits a `ProposedAction` object wrapped in a ```action``` JSON block.
3. PWA shows it as a card in the **Pending Actions** tray.
4. She swipes:
   - **Approve** → action executes (logs to audit)
   - **Edit** → modify before approve
   - **Reject** → discard (logs to audit)
5. She can **whitelist** patterns: "always do this automatically when X is true".

---

## 7. Agent team details

### RemodelAgent
- **Qdrant collection:** `project-remodel`
- **Tools:** `ingest_document`, `draft_email`, `share_with_builder`
- **Typical tier:** Sonnet (briefs) · Haiku (Q&A)
- **Whitelist:** extract product specs → shortlist; vendor quote → tag

### HusbandHealthAgent
- **Qdrant collection:** `project-husband-health`
- **Tools:** `ingest_document`, `create_calendar_event`, `draft_appointment_brief`
- **Typical tier:** Sonnet (briefs) · Haiku (timeline Q&A)
- **Whitelist:** extract appointment dates → calendar; flag contradictions

### OwnHealthAgent
- Mirror of HusbandHealth for the user herself

### CalendarAgent
- Read-only across all projects; surfaces upcoming events; detects conflicts

### InboxAgent
- Receives forwarded items, classifies into the right project, files them

### AgentBuilder (meta)
- Sits in the PWA as "Create new agent"
- Sonnet for synthesis
- Tools: `create_qdrant_collection`, `register_agent`, `seed_whitelist`

---

## 8. Deployment topology

```
┌── Her home computer (Docker Compose) ─────────────────────────────┐
│  caddy → qdrant + tei (bge-small) + faster-whisper + kokoro       │
│         + smollm2-router + docling + smolagents-orchestrator      │
│         + audit-db                                                │
│  watchdog container (restarts unhealthy services)                 │
│  nightly encrypted backup → iCloud/OneDrive                       │
└────────────────────────────────────────────────────────────────────┘
            │                                       │
            │ Cloudflare Tunnel (free)              │
            ▼                                       ▼
   PWA on Vercel (free) ────────────► Anthropic API (Claude)
                                              │
                                              └─→ Haiku / Sonnet / Sonnet+thinking
```

**External health monitoring:**
- UptimeRobot (free) pings every 5 min
- If VPS / laptop is unreachable → SMS alert + auto-restart attempt
- Solves the "agent-monitoring-itself" chicken-and-egg

---

## 9. Future / later (not in v1)

- **On-device SmolLM2** in PWA via `transformers.js` for offline routing
- **Streaming STT** for real-time transcription as she speaks
- **CAD/BIM ingestion** (ODA File Converter + IfcOpenShell) — currently specs + measurements only
- **Hugging Face Pro Space backup** ($2/mo) for 24/7 uptime while traveling
- **Ragas nightly eval** against a held-out set of representative project queries
- **Multi-user support** (single-user is hardcoded today)

---

## 10. References

- [`docs/research/huggingface-research.md`](research/huggingface-research.md) — full HF research findings
- [`README.md`](../README.md) — repo overview + quick start
- [`apps/agent/src/trg/orchestrator/manager.py`](../../apps/agent/src/trg/orchestrator/manager.py) — main chat pipeline
- [`apps/agent/src/trg/orchestrator/agent_builder.py`](../../apps/agent/src/trg/orchestrator/agent_builder.py) — meta-agent
- [`infra/docker-compose.yml`](../../infra/docker-compose.yml) — service stack
