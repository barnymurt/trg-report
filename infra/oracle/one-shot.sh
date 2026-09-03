#!/usr/bin/env bash
# one-shot.sh — single command that does the full bootstrap on a fresh
# Oracle Cloud VM. Installs git if needed, clones the repo, prompts for
# your Anthropic key, runs the stack setup, prints the live URL.
#
# Usage — paste ONE of these from a fresh VM:
#
#   curl -sSL https://raw.githubusercontent.com/barnymurt/trg-report/main/infra/oracle/one-shot.sh | bash
#
# You'll be prompted for your Anthropic API key. Everything else is automatic.

set -euo pipefail

REPO_URL="https://github.com/barnymurt/trg-report.git"
REPO_DIR="$HOME/trg"

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[0;32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[1;33m⚠\033[0m %s\n" "$1"; }

# ─── Preflight ─────────────────────────────────────────────────────────
step "Welcome — this will set up your TRG agent in ~5-10 minutes"
printf "  Running as: %s on %s\n" "$(whoami)" "$(uname -srm)"

# ─── Swap (1 GB VMs OOM during dnf) ─────────────────────────────────────
if [ -f /proc/meminfo ]; then
  TOTAL_MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
  SWAP_MB=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
  if [ "$TOTAL_MEM_MB" -le 1500 ] && [ "$SWAP_MB" -lt 1024 ]; then
    step "Adding 2 GB swap (this VM has ${TOTAL_MEM_MB} MB RAM; dnf will OOM without swap)"
    sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
    ok "swap added (now $(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo) MB)"
  else
    ok "RAM/swap sufficient (${TOTAL_MEM_MB} MB RAM, ${SWAP_MB} MB swap)"
  fi
fi

# ─── Git ────────────────────────────────────────────────────────────────
if ! command -v git >/dev/null 2>&1; then
  step "Installing git"
  if command -v dnf >/dev/null 2>&1; then
    sudo dnf -y install git
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y -qq git
  else
    echo "Don't know how to install git. Please install it manually and re-run."
    exit 1
  fi
fi
ok "git available"

# ─── Clone ─────────────────────────────────────────────────────────────
step "Cloning the repo"
if [ -d "$REPO_DIR" ]; then
  ok "repo already at $REPO_DIR — pulling latest"
  cd "$REPO_DIR" && git pull --ff-only || true
else
  git clone "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
  ok "cloned"
fi

# ─── .env ──────────────────────────────────────────────────────────────
step "Setting up .env"
if [ ! -f .env ]; then
  cp .env.example .env
  ok "copied .env.example -> .env"
fi

# Prompt for the Anthropic key if not already set
if ! grep -qE '^ANTHROPIC_API_KEY=sk-' .env; then
  printf "\n  Paste your Anthropic API key (starts with sk-ant-):\n  > "
  read -rs ANTHROPIC_API_KEY
  echo ""
  if [ -z "$ANTHROPIC_API_KEY" ]; then
    warn "No key provided — chat will use demo mode (canned responses). You can edit .env later."
  else
    sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY|" .env
    ok "Anthropic key set"
  fi
else
  ok "ANTHROPIC_API_KEY already set in .env"
fi

# ─── Bootstrap ──────────────────────────────────────────────────────────
step "Running infra/oracle/setup.sh"
bash infra/oracle/setup.sh
