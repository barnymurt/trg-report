#!/usr/bin/env bash
# Start the TRG agent Space: Qdrant + FastAPI + serves the PWA.
#
# Hugging Face Spaces expects a single port (7860 by default). Qdrant runs
# internally on 6333 and is reached via QDRANT_URL=http://localhost:6333.
# The PWA static export is mounted at /app/web and served by FastAPI at /.

set -euo pipefail

mkdir -p /data/qdrant /data/documents /data/audit

# ─── Qdrant ─────────────────────────────────────────────────────────────
echo "[start] launching qdrant…"
qdrant --storage-snapshots-dir /data/qdrant/snapshots \
       --uri http://0.0.0.0:6333 \
       --disable-telemetry > /data/qdrant.log 2>&1 &
QDRANT_PID=$!

for i in {1..30}; do
  if curl -sf http://localhost:6333/health >/dev/null 2>&1; then
    echo "[start] qdrant healthy"
    break
  fi
  sleep 1
done

# ─── FastAPI agent (serves API + PWA) ───────────────────────────────────
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
export TEI_URL="${TEI_URL:-https://barnymurt-trg-embeddings.hf.space}"
export WHISPER_URL="${WHISPER_URL:-https://barnymurt-trg-voice.hf.space}"
export KOKORO_URL="${KOKORO_URL:-https://barnymurt-trg-voice.hf.space}"
export SMOLLM2_URL="${SMOLLM2_URL:-}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export PWA_STATIC_DIR="${PWA_STATIC_DIR:-/app/web}"

# uvicorn picks up the route we register in main.py to serve /app/web at /
exec uvicorn trg.main:app --host 0.0.0.0 --port 7860 --workers 1 --proxy-headers
