#!/usr/bin/env bash
# TRG Agent Team — Oracle Cloud Always Free one-shot bootstrap.
#
# Runs on a fresh Ubuntu 22.04 / 24.04 ARM VM.Standard.A1.Flex instance.
# Installs Docker, pulls all images, starts the stack, prints a URL.
#
# Usage (after creating the VM in OCI and SSHing in):
#   curl -sSL https://raw.githubusercontent.com/barnymurt/trg-report/main/infra/oracle/setup.sh | bash
#
# Or clone the repo and run locally:
#   git clone https://github.com/barnymurt/trg-report.git trg
#   cd trg
#   cp .env.example .env
#   nano .env                              # set ANTHROPIC_API_KEY
#   bash infra/oracle/setup.sh
#
# Idempotent: safe to re-run.

set -euo pipefail

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
NC=$'\033[0m'

step() { printf "${BOLD}${BLUE}==>${NC} %s\n" "$1"; }
ok()   { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${NC} %s\n" "$1"; }
die()  { printf "  ${RED}✗${NC} %s\n" "$1"; exit 1; }

REPO_URL="${TRG_REPO_URL:-https://github.com/barnymurt/trg-report.git}"
REPO_DIR="${TRG_DIR:-$HOME/trg}"

# ─── Preflight ─────────────────────────────────────────────────────────
step "Preflight"
[ "$(id -u)" -eq 0 ] && die "Run as the ubuntu user (not root). The script uses sudo when needed."
command -v curl >/dev/null || die "curl required"
command -v git  >/dev/null || die "git required"
ok "running as $(whoami) on $(uname -srm)"

# ─── Docker ─────────────────────────────────────────────────────────────
step "Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  ok "docker installed"
else
  ok "docker already installed ($(docker --version 2>/dev/null || echo unknown))"
fi

# Allow ubuntu user to run docker without sudo
if ! groups | grep -q docker; then
  sudo usermod -aG docker "$USER"
  warn "added $USER to docker group — log out and back in (or run: newgrp docker)"
fi

# ─── Clone the repo ────────────────────────────────────────────────────
step "Cloning TRG repository"
if [ -d "$REPO_DIR" ]; then
  ok "repo already at $REPO_DIR (pulling latest)"
  cd "$REPO_DIR"
  git pull --ff-only || warn "git pull failed — continuing with existing checkout"
else
  git clone "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
  ok "cloned to $REPO_DIR"
fi

# ─── .env file ─────────────────────────────────────────────────────────
step "Configuring .env"
if [ ! -f .env ]; then
  cp .env.example .env
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}|" .env
    ok "ANTHROPIC_API_KEY set from env"
  else
    warn ".env created from template. Edit it now to set ANTHROPIC_API_KEY:"
    warn "  nano $REPO_DIR/.env"
    warn "Then re-run: bash infra/oracle/setup.sh"
    # Continue anyway — services can still start, chat will use demo mode
  fi
else
  ok ".env already exists"
fi

# ─── Container swap / memory ───────────────────────────────────────────
step "Tuning VM for Docker (ARM, 24 GB)"
# Increase vm.max_map_count for Qdrant
if ! grep -q "vm.max_map_count=262144" /etc/sysctl.conf; then
  echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf >/dev/null
  sudo sysctl -p >/dev/null
fi
ok "vm.max_map_count=262144"

# ─── Start the stack ───────────────────────────────────────────────────
step "Starting Docker Compose stack"
newgrp docker 2>/dev/null || true
docker compose -f infra/docker-compose.yml pull --ignore-pull-failures
docker compose -f infra/docker-compose.yml up -d

ok "stack started"

# ─── Wait for agent health ─────────────────────────────────────────────
step "Waiting for agent /health (this can take 2-3 min for first-time image pulls)…"
for i in {1..60}; do
  if curl -sf http://localhost:8001/health >/dev/null 2>&1; then
    ok "agent healthy"
    break
  fi
  if [ "$i" -eq 60 ]; then
    warn "agent not yet healthy after 60s. Check: docker compose -f infra/docker-compose.yml logs agent"
  fi
  sleep 5
done

# ─── Cloudflare quick tunnel ───────────────────────────────────────────
step "Starting Cloudflare quick tunnel"
if ! command -v cloudflared >/dev/null 2>&1; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    aarch64) CFD_ARCH="arm64" ;;
    x86_64)  CFD_ARCH="amd64" ;;
    *) die "unsupported arch $ARCH" ;;
  esac
  wget -qO /tmp/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CFD_ARCH}"
  sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
  sudo chmod +x /usr/local/bin/cloudflared
  ok "cloudflared installed"
fi

# Run tunnel in background, write logs
nohup cloudflared tunnel --no-autoupdate --url http://localhost:8001 \
  > /tmp/cloudflared.log 2>&1 &
echo $! > /tmp/cloudflared.pid

# Wait for the URL to appear in the log
for i in {1..30}; do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -n 1 || true)
  if [ -n "$URL" ]; then break; fi
  sleep 2
done

# ─── Summary ───────────────────────────────────────────────────────────
step "Summary"
echo ""
echo -e "  ${GREEN}✓ Docker stack is running${NC}"
echo -e "  ${GREEN}✓ Agent API on http://localhost:8001${NC}"
echo -e "  ${GREEN}✓ PWA served at / by the same FastAPI${NC}"
echo ""
if [ -n "$URL" ]; then
  echo -e "  ${BOLD}PUBLIC URL (Cloudflare quick tunnel):${NC}"
  echo -e "  ${BLUE}${URL}${NC}"
  echo ""
  echo -e "  ${YELLOW}This URL is random and will change on the next VM restart.${NC}"
  echo -e "  ${YELLOW}For a persistent URL, see: https://github.com/barnymurt/trg-report/blob/main/infra/oracle/DEPLOY.md#step-5--cloudflare-tunnel-free-url${NC}"
else
  echo -e "  ${YELLOW}Cloudflare tunnel didn't print a URL. Check: tail -f /tmp/cloudflared.log${NC}"
fi
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo "    1. Open the URL above on your phone — should see the chat UI"
echo "    2. Tap the mic → speak → see demo responses (no Anthropic key needed)"
echo "    3. Edit \$REPO_DIR/.env and set ANTHROPIC_API_KEY for real Claude"
echo "    4. Re-run: bash $REPO_DIR/infra/oracle/setup.sh"
echo ""
ok "done"
