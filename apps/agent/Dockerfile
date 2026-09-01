FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for python-magic, audio handling, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install . && \
    pip install .[dev] || true

# Copy source
COPY src/ ./src/
COPY README.md ./

# Data directory for audit DB, agent config, etc.
RUN mkdir -p /app/data/audit /app/data/config /app/data/documents

ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "trg.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
