#!/usr/bin/env bash
# install-native.sh — bare-metal fallback installer.
#
# If Docker refuses to behave on the target machine, this script installs
# each service natively (no containers). Slower, more platform-specific,
# but works without Docker Desktop.
#
# Usage:
#   bash infra/scripts/install-native.sh            # interactive
#   bash infra/scripts/install-native.sh --dry-run  # print actions, do nothing
#   bash infra/scripts/install-native.sh --service qdrant   # install one service

set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OS="$(uname -s)"

DRY_RUN=0
SINGLE=""
while [ "${1:-}" != "" ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --service) shift; SINGLE="${1:-}" ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
  shift
done

# ─── Output helpers ──────────────────────────────────────────────────────

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
NC=$'\033[0m'

step() { printf "${BOLD}${BLUE}→${NC} %s\n" "$1"; }
ok()   { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${NC} %s\n" "$1"; }
err()  { printf "  ${RED}✗${NC} %s\n" "$1"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "    ${YELLOW}DRY${NC} %s\n" "$*"
  else
    "$@"
  fi
}

# ─── Detect package manager ──────────────────────────────────────────────

detect_pkg_mgr() {
  if command -v brew >/dev/null 2>&1; then echo "brew"
  elif command -v apt-get >/dev/null 2>&1; then echo "apt"
  elif command -v dnf >/dev/null 2>&1; then echo "dnf"
  elif command -v pacman >/dev/null 2>&1; then echo "pacman"
  elif command -v choco >/dev/null 2>&1; then echo "choco"
  elif command -v winget >/dev/null 2>&1; then echo "winget"
  else echo "unknown"
  fi
}

PKG_MGR="$(detect_pkg_mgr)"
DATA_DIR="$REPO_ROOT/data"
mkdir -p "$DATA_DIR/qdrant" "$DATA_DIR/hf-cache" "$DATA_DIR/whisper-cache" "$DATA_DIR/smollm2-cache" "$DATA_DIR/kokoro-cache" "$DATA_DIR/docling-cache"

printf "${BOLD}TRG Agent Team — native installer${NC}\n"
printf "  OS: %s\n" "$OS"
printf "  Package manager: %s\n" "$PKG_MGR"
printf "  Mode: %s\n" "$([ "$DRY_RUN" -eq 1 ] && echo 'DRY RUN' || echo 'LIVE')"
printf "  Data dir: %s\n\n" "$DATA_DIR"

# ─── Service installers ──────────────────────────────────────────────────

install_qdrant() {
  step "Qdrant vector DB"
  case "$OS" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        run brew install qdrant
      else
        warn "Install Homebrew first, or download from https://github.com/qdrant/qdrant/releases"
      fi
      ;;
    Linux)
      # Pre-built binary
      ARCH="$(uname -m)"
      case "$ARCH" in
        x86_64) QARCH="x86_64-unknown-linux-gnu" ;;
        aarch64) QARCH="aarch64-unknown-linux-gnu" ;;
        *) err "Unsupported arch $ARCH"; return 1 ;;
      esac
      QVER="v1.12.0"
      QBIN="$DATA_DIR/qdrant"
      if [ ! -x "$QBIN" ]; then
        run curl -sLo "$DATA_DIR/qdrant.tgz" \
          "https://github.com/qdrant/qdrant/releases/download/${QVER}/qdrant-${QARCH}.tar.gz"
        run tar -xzf "$DATA_DIR/qdrant.tgz" -C "$DATA_DIR"
        run chmod +x "$QBIN"
      fi
      ok "qdrant at $QBIN"
      ;;
    MINGW*|MSYS*|CYGWIN*|Windows*)
      warn "Native Qdrant on Windows is not directly supported. Use Docker, or run qdrant inside WSL2."
      ;;
  esac
}

install_tei() {
  step "Text Embeddings Inference (bge-small + bge-m3 + reranker)"
  if command -v cargo >/dev/null 2>&1; then
    run cargo install --git https://github.com/huggingface/text-embeddings-inference
    ok "tei installed via cargo"
  else
    warn "Cargo not installed. Install Rust from https://rustup.rs/, then re-run."
    warn "Alternative: use the Docker image even on a non-Docker machine via rancher-desktop or similar."
  fi
}

install_whisper() {
  step "faster-whisper (STT)"
  case "$OS" in
    Darwin|Linux|MINGW*|MSYS*|CYGWIN*|Windows*)
      PY="$(command -v python3 || command -v python)"
      if [ -z "$PY" ]; then
        warn "Python 3 not installed"
        return 1
      fi
      run "$PY" -m pip install --user faster-whisper
      ok "faster-whisper installed (model downloads on first use)"
      ;;
  esac
}

install_kokoro() {
  step "Kokoro-82M (TTS)"
  case "$OS" in
    Darwin|Linux|MINGW*|MSYS*|CYGWIN*|Windows*)
      PY="$(command -v python3 || command -v python)"
      if [ -z "$PY" ]; then
        warn "Python 3 not installed"
        return 1
      fi
      run "$PY" -m pip install --user kokoro-onnx
      ok "kokoro-onnx installed (models download on first run)"
      ;;
  esac
}

install_smollm2() {
  step "SmolLM2-1.7B-Instruct (local LLM)"
  PY="$(command -v python3 || command -v python)"
  if [ -z "$PY" ]; then
    warn "Python 3 not installed"
    return 1
  fi
  run "$PY" -m pip install --user llama-cpp-python
  # Pre-download the GGUF
  GGUF_PATH="$DATA_DIR/smollm2-cache/smollm2-1.7b-instruct-q4_k_m.gguf"
  if [ ! -f "$GGUF_PATH" ]; then
    run curl -sLo "$GGUF_PATH" \
      "https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF/resolve/main/smollm2-1.7b-instruct-q4_k_m.gguf"
  fi
  ok "SmolLM2 GGUF at $GGUF_PATH"
}

install_docling() {
  step "Docling (document ingest)"
  PY="$(command -v python3 || command -v python)"
  if [ -z "$PY" ]; then
    warn "Python 3 not installed"
    return 1
  fi
  run "$PY" -m pip install --user docling
  ok "docling installed"
}

install_agent_deps() {
  step "Agent backend Python deps"
  PY="$(command -v python3 || command -v python)"
  if [ -z "$PY" ]; then
    warn "Python 3 not installed"
    return 1
  fi
  run "$PY" -m pip install --user -e "$REPO_ROOT/apps/agent"
  ok "agent backend installed (editable mode)"
}

# ─── Write a native env file pointing at the right URLs ───────────────

write_native_env() {
  step "Writing infra/.native.env"
  NATIVE_ENV="$REPO_ROOT/infra/.native.env"
  cat > "$NATIVE_ENV" <<EOF
# Generated by install-native.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Source this before starting the agent backend: \`. infra/.native.env\`

QDRANT_URL=http://localhost:6333
TEI_URL=http://localhost:8080
RERANKER_URL=http://localhost:8081
WHISPER_URL=http://localhost:9000
KOKORO_URL=http://localhost:8880
SMOLLM2_URL=http://localhost:8000
DOCLING_URL=http://localhost:5001

# Data paths
QDRANT_STORAGE_PATH=$DATA_DIR/qdrant
DOCUMENT_STORE_PATH=$DATA_DIR/documents
AUDIT_DB_PATH=$DATA_DIR/audit.db

# Model paths
SMOLLM2_MODEL_PATH=$DATA_DIR/smollm2-cache/smollm2-1.7b-instruct-q4_k_m.gguf
WHISPER_CACHE=$DATA_DIR/whisper-cache
HF_CACHE=$DATA_DIR/hf-cache
EOF
  ok "wrote $NATIVE_ENV"
  printf "\n  ${YELLOW}→${NC} Start each service manually. See scripts/start-native.sh (TODO).\n"
}

# ─── Run ─────────────────────────────────────────────────────────────────

if [ -n "$SINGLE" ]; then
  case "$SINGLE" in
    qdrant) install_qdrant ;;
    tei) install_tei ;;
    whisper) install_whisper ;;
    kokoro) install_kokoro ;;
    smollm2) install_smollm2 ;;
    docling) install_docling ;;
    agent) install_agent_deps ;;
    *) err "unknown service: $SINGLE"; exit 2 ;;
  esac
else
  install_qdrant
  install_tei
  install_whisper
  install_kokoro
  install_smollm2
  install_docling
  install_agent_deps
  write_native_env
fi

printf "\n${GREEN}Native install complete.${NC}\n"
printf "Next: start each service, then run the agent backend with the native env sourced.\n"
