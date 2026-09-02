#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data
echo "[voice] preloading Whisper model distil-large-v3 (CPU int8)…"
python -c "from faster_whisper import WhisperModel; WhisperModel('distil-whisper/distil-large-v3', device='cpu', compute_type='int8', download_root='/app/data')" || true

echo "[voice] starting uvicorn…"
exec uvicorn server:app --host 0.0.0.0 --port 7860 --workers 1 --proxy-headers
