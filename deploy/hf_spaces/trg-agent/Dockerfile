# TRG Agent — Hugging Face Space
#
# This Space runs the full agent backend: FastAPI + Qdrant + SmolLM2.
# It calls out to:
#   - Anthropic API for Claude (reasoning LLM)
#   - HF Inference Endpoints / TEI on the companion `trg-embeddings` Space
#   - HF Inference Endpoints / faster-whisper on the companion `trg-voice` Space
#
# Private Space (requires HF Pro); persistent storage on HF Hub Datasets.

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

# Install llama.cpp (for SmolLM2 server, single-binary alternative to llama-cpp-python)
RUN mkdir -p /opt/llama.cpp && \
    cd /opt/llama.cpp && \
    curl -sLo llama.cpp.tar.gz https://github.com/ggerganov/llama.cpp/archive/refs/tags/b3848.tar.gz && \
    tar -xzf llama.cpp.tar.gz --strip-components=1 && \
    rm llama.cpp.tar.gz && \
    (cmake -B build && cmake --build build --config Release --target llama-server -j$(nproc) || true)

WORKDIR /app

# Install Python deps (use the project pyproject)
COPY apps/agent/pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install \
      "smolagents>=1.10.0" "litellm>=1.51.0" "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" \
      "pydantic>=2.9.0" "pydantic-settings>=2.6.0" "anthropic>=0.39.0" \
      "qdrant-client>=1.12.0" "httpx>=0.27.0" "aiosqlite>=0.20.0" \
      "sqlmodel>=0.0.22" "PyJWT>=2.9.0" "loguru>=0.7.0" \
      "tenacity>=9.0.0" "python-dotenv>=1.0.0" "pydub>=0.25.0" \
      "structlog>=24.4.0" "pyyaml>=6.0"

# Copy source
COPY apps/agent/src/ ./src/
COPY README.md ./

ENV PYTHONPATH=/app/src

# Qdrant storage lives here (persisted via HF Spaces persistent storage at /data)
ENV QDRANT_STORAGE=/data/qdrant
ENV AUDIT_DB_PATH=/data/audit.db
ENV DOCUMENT_STORE_PATH=/data/documents

# Hugging Face Space port
EXPOSE 7860

# Start script: Qdrant in background → wait for health → llama-server (optional) → uvicorn
COPY deploy/hf_spaces/trg-agent/start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
