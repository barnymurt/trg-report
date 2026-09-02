# TRG Agent — Hugging Face Space (single all-in-one container)
#
# Runs FastAPI + Qdrant + serves the PWA static export.
# Companion Spaces:
#   - barnymurt/trg-voice       (Whisper + Kokoro)
#   - barnymurt/trg-embeddings  (TEI bge-small)
#
# Single URL: https://barnymurt-trg-agent.hf.space serves both the API
# (/chat, /actions/execute, etc.) and the PWA at /.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps: ffmpeg for audio, qdrant binary
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        curl \
        ca-certificates \
        wget \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Qdrant (CPU build)
ARG QDRANT_VERSION=1.12.0
RUN arch=$(uname -m) && \
    case "$arch" in \
      x86_64) qarch="x86_64-unknown-linux-gnu" ;; \
      aarch64) qarch="aarch64-unknown-linux-gnu" ;; \
    esac && \
    wget -qO /tmp/qdrant.tgz \
      "https://github.com/qdrant/qdrant/releases/download/v${QDRANT_VERSION}/qdrant-${qarch}.tar.gz" && \
    tar -xzf /tmp/qdrant.tgz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/qdrant && \
    rm /tmp/qdrant.tgz

WORKDIR /app

# Install Python deps
RUN pip install --upgrade pip && \
    pip install \
      "smolagents>=1.10.0" "litellm>=1.51.0" "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" \
      "pydantic>=2.9.0" "pydantic-settings>=2.6.0" "anthropic>=0.39.0" \
      "qdrant-client>=1.12.0" "httpx>=0.27.0" "aiosqlite>=0.20.0" \
      "sqlmodel>=0.0.22" "PyJWT>=2.9.0" "loguru>=0.7.0" \
      "tenacity>=9.0.0" "python-dotenv>=1.0.0" "pydub>=0.25.0" \
      "structlog>=24.4.0" "pyyaml>=6.0"

# Copy source
COPY src/ ./src/
COPY pyproject.toml ./

# Copy the prebuilt PWA static export
COPY web/ ./web/

ENV PYTHONPATH=/app/src

# Hugging Face Space persistent storage
ENV QDRANT_STORAGE=/data/qdrant
ENV AUDIT_DB_PATH=/data/audit.db
ENV DOCUMENT_STORE_PATH=/data/documents

EXPOSE 7860

COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
