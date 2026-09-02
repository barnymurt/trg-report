#!/usr/bin/env bash
# Start the TRG agent Space: Qdrant + (optional) llama.cpp + FastAPI.
#
# Hugging Face Spaces expects a single port (7860 by default). We expose
# only the FastAPI; Qdrant runs internally on 6333 and is reached via the
# agent's QDRANT_URL=http://localhost:6333.

set -euo pipefail

mkdir -p /data/qdrant /data/documents /data/audit

# ─── Qdrant ─────────────────────────────────────────────────────────────
echo "[start] launching qdrant…"
qdrant --storage-snapshots-dir /data/qdrant/snapshots \
       --uri http://0.0.0.0:6333 \
       --disable-telemetry > /data/qdrant.log 2>&1 &
QDRANT_PID=$!

# Wait for Qdrant to be healthy
for i in {1..30}; do
  if curl -sf http://localhost:6333/health >/dev/null 2>&1; then
    echo "[start] qdrant healthy"
    break
  fi
  sleep 1
done

# ─── FastAPI agent ──────────────────────────────────────────────────────
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
export TEI_URL="${TEI_URL:-https://barnymurt-trg-embeddings.hf.space}"
export RERANKER_URL="${RERANKER_URL:-https://barnymurt-trg-embeddings.hf.space}"
export WHISPER_URL="${WHISPER_URL:-https://barnymurt-trg-voice.hf.space}"
export KOKORO_URL="${KOKORO_URL:-https://barnymurt-trg-voice.hf.space}"
export SMOLLM2_URL="${SMOLLM2_URL:-http://localhost:8000}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

# HF Spaces exposes port 7860
exec uvicorn trg.main:app --host 0.0.0.0 --port 7860 --workers 1 --proxy-headers
