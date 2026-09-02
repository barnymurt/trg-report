---
title: TRG Agent
emoji: 🧠
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Multi-agent Claude system with RAG and project isolation
---

# TRG Agent

See the main repo: <https://github.com/barnymurt/trg-report>

This Space is the backend for the TRG multi-agent Claude system. It exposes:
- `POST /chat` — full chat pipeline (SmolLM2 routing → Qdrant retrieval → Claude reasoning → NLI faithfulness)
- `POST /actions/execute` — turn approved ProposedActions into real effects (.ics, .eml, .md files)
- `GET /agents`, `GET /audit`, `GET /builder/chat`, `POST /ingest`

## Companion Spaces

- `barnymurt/trg-voice` — Whisper STT + Kokoro TTS
- `barnymurt/trg-embeddings` — TEI embeddings + reranker

## Environment variables

Required (set in Space Settings → Variables):
- `ANTHROPIC_API_KEY` — your Anthropic API key

Optional (defaults work if companion Spaces exist):
- `TEI_URL`, `RERANKER_URL`, `WHISPER_URL`, `KOKORO_URL`, `SMOLLM2_URL`
- `TRG_DEMO_MODE` — set to `true` to use canned responses (no API credits needed)

## Storage

Persistent storage on `/data` (HF Spaces volume). Backs up nightly via the GitHub Action in `.github/workflows/backup.yml`.
