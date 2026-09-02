# TRG Voice — Whisper STT + Kokoro TTS
#
# Combined Space: faster-whisper for /v1/audio/transcriptions,
# Kokoro for /v1/audio/speech. Two services on one HF Space.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip && \
    pip install \
      "fastapi>=0.115.0" \
      "uvicorn[standard]>=0.32.0" \
      "python-multipart>=0.0.12" \
      "faster-whisper>=1.0.0" \
      "kokoro-onnx>=0.4.0" \
      "numpy>=1.26.0" \
      "httpx>=0.27.0"

COPY deploy/hf_spaces/trg-voice/server.py /app/server.py
COPY deploy/hf_spaces/trg-voice/start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 7860

CMD ["/app/start.sh"]
