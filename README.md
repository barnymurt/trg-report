# TRG Agent Team

A multi-agent Claude system with RAG, voice input/output, and project isolation. Designed for a single mobile-first user (a retired public-health professor) running several concurrent life-projects: house remodel, husband's health, own health, plus on-demand sub-projects created via an **AgentBuilder** meta-agent.

**The pitch in one sentence:** A voice-first, mobile-first PWA that gives a tired-but-sophisticated user a team of Claude-powered agents that can propose actions, cite sources, and respect her final approval — without being another energy drain.

## Stack at a glance

- **LLM (reasoning):** Claude via Anthropic API — Haiku / Sonnet / Sonnet+extended-thinking, tier auto-selected by task difficulty
- **LLM (routing + compression + summarisation):** `HuggingFaceTB/SmolLM2-1.7B-Instruct` — local, free, keeps Claude tokens focused on comprehension
- **Embeddings:** `BAAI/bge-small-en-v1.5` (EN, fast) + `BAAI/bge-m3` (multilingual / long-doc, hybrid dense+sparse)
- **Reranker:** `BAAI/bge-reranker-v2-m3`
- **STT:** `distil-whisper/distil-large-v3` via faster-whisper
- **TTS:** `hexgrad/Kokoro-82M`
- **Document ingest:** `ibm-granite/granite-docling-258M` + docling
- **Vector DB:** Qdrant (multi-collection, hybrid)
- **Agent orchestration:** `huggingface/smolagents`
- **Web app:** Next.js 14 (PWA, Tailwind, shadcn/ui)
- **Backend:** FastAPI + smolagents
- **Reverse proxy / tunnel:** Caddy + Cloudflare Tunnel (free)

Full research in [`docs/research/huggingface-research.md`](docs/research/huggingface-research.md).
Full architecture in [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

## Repo layout

```
.
├── apps/
│   ├── web/        # Next.js PWA (mobile-first chat + voice)
│   └── agent/      # Python backend (smolagents + FastAPI)
├── packages/
│   └── shared/     # Shared TypeScript types
├── infra/
│   ├── docker-compose.yml
│   ├── caddy/      # Reverse proxy config
│   ├── cloudflare/ # Tunnel config example
│   └── scripts/    # Backup, healthcheck, power-setup
├── docs/
│   ├── research/
│   └── architecture/
└── ...
```

## Quick start

> Requires: Node 20+, pnpm 9+ (via corepack), Docker, Python 3.12+, an Anthropic API key.

```bash
# 1. Enable pnpm via corepack
corepack enable

# 2. Install deps
pnpm install

# 3. Configure
cp .env.example .env
# edit .env — at minimum set ANTHROPIC_API_KEY

# 4. Boot the local infrastructure (Qdrant, TEI, Whisper, Kokoro, SmolLM2)
pnpm infra:up

# 5. Pull model weights (one-time)
docker compose -f infra/docker-compose.yml run --rm tei-pull
docker compose -f infra/docker-compose.yml run --rm smollm2-pull
docker compose -f infra/docker-compose.yml run --rm whisper-pull

# 6. Run the apps
pnpm dev
```

Open the PWA at <http://localhost:3000>. Talk to it.

## Privacy posture

- All embeddings / STT / TTS / routing LLM / document parsing run on local hardware.
- Only the LLM reasoning calls hit Anthropic's API.
- Every Claude call is logged in an audit DB — viewable in the PWA ("Show me everything sent to Anthropic").
- One-button right-to-delete for any project.
- See [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md#privacy-and-data-governance).

## Cost controls

- Local TEI / Whisper / Kokoro / SmolLM2 → near-zero marginal cost per interaction.
- Compression to ≤ 3k tokens before any Claude call.
- Auto tier selection: trivial → SmolLM2, medium → Haiku, hard → Sonnet, expert → Sonnet+thinking.
- Faithfulness NLI flags low-confidence answers; auto-retry on a higher tier.
- Monthly budget cap per project (configurable).

## Contributing / status

This is an early-stage build. See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for the full design and `apps/agent/src/` for the runtime components.

## License

Private. All model licenses are tracked in [`docs/research/huggingface-research.md`](docs/research/huggingface-research.md).
