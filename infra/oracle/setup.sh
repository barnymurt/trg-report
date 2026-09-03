#!/usr/bin/env bash
# TRG Agent Team — Oracle Cloud Always Free one-shot bootstrap.
#
# Runs on Ubuntu 22.04/24.04 OR Oracle Linux 8/9 (ARM or x86).
# Installs Docker, pulls all images, starts the stack, prints a URL.
#
# Adapts to available RAM:
#   < 4 GB  : just the agent + Qdrant; uses HF Inference API for everything else
#   4-8 GB  : agent + Qdrant + embeddings + whisper + kokoro
#   > 8 GB  : full stack including SmolLM2 routing
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
#
# Required env vars (optional):
#   HF_TOKEN — if set, used for HF Inference API (better quality embeddings
#              + reranking than local bge-small on tiny VMs).
#   ANTHROPIC_API_KEY — your Claude key (or set in .env after cloning)
#
# Optional env vars:
#   TRG_REPO_URL — defaults to https://github.com/barnymurt/trg-report.git
#   TRG_DIR      — defaults to ~/trg

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
[ "$(id -u)" -eq 0 ] && die "Run as the unprivileged user (ubuntu or opc). The script uses sudo when needed."
command -v curl >/dev/null || die "curl required"
# git is optional — only used for `git pull` updates. The bootstrap tarball
# download path (used on tiny VMs that can't install git) doesn't need it.
if ! command -v git >/dev/null 2>&1; then
  warn "git not installed — updates will require downloading a fresh tarball"
fi

# Detect OS
. /etc/os-release 2>/dev/null || die "Could not detect OS from /etc/os-release"
case "${ID:-unknown}:${VERSION_ID:-0}" in
    ubuntu:*|ubuntu:2*|ubuntu:24*|debian:*) OS_FAMILY="debian" ;;
    ol:*|oraclelinux:*)                       OS_FAMILY="rhel" ;;
    rhel:*|centos:*|rocky:*|almalinux:*)      OS_FAMILY="rhel" ;;
    *) die "Unsupported OS: ${ID} ${VERSION_ID}" ;;
esac
ok "OS: ${PRETTY_NAME:-unknown} (${OS_FAMILY})"

# Detect RAM
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_RAM_GB=$((TOTAL_RAM_KB / 1024 / 1024))
ok "RAM: ${TOTAL_RAM_GB} GB"

# Pick which services we can afford
if   [ "$TOTAL_RAM_GB" -ge 12 ]; then PROFILE="full"
elif [ "$TOTAL_RAM_GB" -ge 6  ]; then PROFILE="core"
elif [ "$TOTAL_RAM_GB" -ge 2  ]; then PROFILE="minimal"
else PROFILE="minimal"
fi
ok "deployment profile: $PROFILE"

# ─── Docker install (handles both Ubuntu and Oracle/RHEL families) ──────
step "Installing Docker"

install_docker_debian() {
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

install_docker_rhel() {
  # Oracle Linux 8/9 ships with podman; install Docker CE from the official repo.
  sudo dnf -y install dnf-utils yum-utils
  sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo systemctl enable --now docker
}

install_docker_static() {
  # Used on memory-constrained VMs (E2.1.Micro, 498 MB) where dnf OOMs.
  # Downloads a precompiled tarball from docker.com — no package manager.
  local ver="${DOCKER_STATIC_VERSION:-27.3.1}"
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64)  darch="x86_64" ;;
    aarch64) darch="aarch64" ;;
    *) die "unsupported arch for static docker: $arch" ;;
  esac
  local url="https://download.docker.com/linux/static/stable/${darch}/docker-${ver}.tgz"
  step "Downloading static Docker ${ver} (${darch})"
  curl -sLo /tmp/docker.tgz "$url"
  sudo tar -xzf /tmp/docker.tgz -C /usr/local/bin --strip-components=1 docker/docker docker/dockerd docker/docker-init docker/containerd docker/containerd-shim* docker/runc docker/ctr
  rm /tmp/docker.tgz

  # Set up the systemd unit
  sudo tee /etc/systemd/system/docker.service >/dev/null <<'EOF'
[Unit]
Description=Docker Application Container Engine
Documentation=https://docs.docker.com
After=network-online.target firewalld.service
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd -H unix:///var/run/docker.sock --data-root /var/lib/docker
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutSec=0
RestartSec=2
Restart=always
StartLimitBurst=3
StartLimitInterval=60s
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
Delegate=yes
KillMode=process

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now docker
  ok "docker installed (static, v${ver})"
}

# Check for docker in standard locations (PATH may not include /usr/local/bin
# when running under sudo, so don't rely on `command -v` alone)
DOCKER_BIN=""
for candidate in /usr/local/bin/docker /usr/bin/docker /snap/bin/docker; do
  [ -x "$candidate" ] && DOCKER_BIN="$candidate" && break
done
[ -z "$DOCKER_BIN" ] && command -v docker >/dev/null 2>&1 && DOCKER_BIN="$(command -v docker)"

if [ -n "$DOCKER_BIN" ]; then
  ok "docker found at $DOCKER_BIN ($($DOCKER_BIN --version 2>&1 | head -1))"
elif [ "$TOTAL_RAM_GB" -lt 1 ] && command -v curl >/dev/null 2>&1; then
  install_docker_static
else
  case "$OS_FAMILY" in
    debian) install_docker_debian ;;
    rhel)   install_docker_rhel   ;;
  esac
  ok "docker installed"
fi

# Make sure the compose plugin exists (or fall back to a static binary)
if [ -n "$DOCKER_BIN" ] && ! $DOCKER_BIN compose version >/dev/null 2>&1; then
  step "Installing docker compose plugin (static)"
  COMPOSE_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)"
  curl -sLo /tmp/docker-compose "$COMPOSE_URL"
  sudo mkdir -p /usr/local/libexec/docker/cli-plugins
  sudo install -m 0755 /tmp/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
  rm /tmp/docker-compose
  ok "compose plugin installed"
fi

# Allow current user to run docker without sudo
if ! groups | grep -q docker; then
  sudo usermod -aG docker "$USER"
  warn "added $USER to docker group — log out and back in (or run: newgrp docker)"
  warn "Re-run this script after re-login."
  exit 0
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
  fi
  if [ -n "${HF_TOKEN:-}" ]; then
    sed -i "s|^HF_TOKEN=.*|HF_TOKEN=${HF_TOKEN}|" .env
    ok "HF_TOKEN set from env"
  fi
  warn ".env created from template. If you didn't pass ANTHROPIC_API_KEY, edit it now:"
  warn "  nano $REPO_DIR/.env"
  warn "Then re-run this script."
else
  ok ".env already exists"
fi

# ─── Adapt docker-compose for the chosen profile ──────────────────────
step "Configuring docker-compose for profile=$PROFILE"
COMPOSE_FILE="infra/docker-compose.yml"
COMPOSE_OVERRIDE="infra/docker-compose.${PROFILE}.yml"

# Always stop any prior stack
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true

# Write a profile-specific override file
cat > "$COMPOSE_OVERRIDE" <<EOF
# Auto-generated by infra/oracle/setup.sh for profile=$PROFILE
# Do not edit — regenerated on every setup run.
services:
EOF

case "$PROFILE" in
  full)
    # everything
    cat >> "$COMPOSE_OVERRIDE" <<EOF
  smollm2:
    deploy:
      resources:
        limits:
          memory: 4G
EOF
    ok "starting full stack (agent, Qdrant, TEI, reranker, whisper, kokoro, smollm2, docling)"
    ;;
  core)
    cat >> "$COMPOSE_OVERRIDE" <<EOF
  tei-multilingual:
    deploy:
      resources:
        limits:
          memory: 256M
  docling:
    deploy:
      resources:
        limits:
          memory: 768M
  smollm2:
    deploy:
      resources:
        limits:
          memory: 1G
EOF
    ok "starting core stack (no reranker, no docling, smaller TEI)"
    ;;
  minimal)
    # Drop everything but agent + Qdrant + the lightest embedder
    cat >> "$COMPOSE_OVERRIDE" <<EOF
  tei-multilingual:
    deploy:
      resources:
        limits:
          memory: 128M
  docling:
    deploy:
      resources:
        limits:
          memory: 0    # sentinel: orchestrator will skip starting it
  smollm2:
    deploy:
      resources:
        limits:
          memory: 0
EOF
    # Drop heavy services entirely on tiny VMs
    sed -i 's/^\s*-\s*tei-multilingual$/# & disabled on minimal profile/' "$COMPOSE_FILE" 2>/dev/null || true
    sed -i 's/^\s*-\s*whisper$/# & disabled on minimal profile/' "$COMPOSE_FILE" 2>/dev/null || true
    sed -i 's/^\s*-\s*kokoro$/# & disabled on minimal profile/' "$COMPOSE_FILE" 2>/dev/null || true
    sed -i 's/^\s*-\s*docling$/# & disabled on minimal profile/' "$COMPOSE_FILE" 2>/dev/null || true
    warn "starting minimal stack (agent + Qdrant + bge-small only)"
    warn "voice + reranker + docling are disabled; will use HF Inference API"
    ;;
esac

# ─── Qdrant tuning ─────────────────────────────────────────────────────
step "Tuning vm.max_map_count for Qdrant"
if ! grep -q "vm.max_map_count=262144" /etc/sysctl.conf 2>/dev/null; then
  echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf >/dev/null
  sudo sysctl -p >/dev/null
fi
ok "vm.max_map_count=262144"

# ─── Start the stack ───────────────────────────────────────────────────
step "Starting Docker Compose stack"
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" pull --ignore-pull-failures 2>&1 | tail -n 5
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" up -d 2>&1 | tail -n 10
ok "stack started"

# ─── Wait for agent health ─────────────────────────────────────────────
step "Waiting for agent /health (up to 5 min for first-time image pulls)…"
HEALTHY=false
for i in {1..60}; do
  if curl -sf http://localhost:8001/health >/dev/null 2>&1; then
    ok "agent healthy (took ${i}×5s)"
    HEALTHY=true
    break
  fi
  sleep 5
done

if [ "$HEALTHY" != "true" ]; then
  warn "agent not healthy after 5 min. Last 30 log lines:"
  docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" logs --tail=30 agent 2>&1 | tail -n 30
fi

# ─── Cloudflare quick tunnel ───────────────────────────────────────────
step "Starting Cloudflare quick tunnel"
if ! command -v cloudflared >/dev/null 2>&1; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    aarch64) CFD_ARCH="arm64" ;;
    x86_64)  CFD_ARCH="amd64" ;;
    *) die "unsupported arch $ARCH" ;;
  esac
  curl -sLo /tmp/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CFD_ARCH}"
  sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
  sudo chmod +x /usr/local/bin/cloudflared
  ok "cloudflared installed"
fi

# Run tunnel in background
nohup cloudflared tunnel --no-autoupdate --url http://localhost:8001 \
  > /tmp/cloudflared.log 2>&1 &
echo $! > /tmp/cloudflared.pid

URL=""
for i in {1..30}; do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -n 1 || true)
  if [ -n "$URL" ]; then break; fi
  sleep 2
done

# ─── systemd watchdog so the stack survives reboots ──────────────────
step "Installing systemd watchdog (so the stack restarts on VM reboot)"
WATCHDOG_UNIT="/etc/systemd/system/trg-watchdog.service"
sudo tee "$WATCHDOG_UNIT" >/dev/null <<EOF
[Unit]
Description=TRG Agent Team watchdog
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REPO_DIR
ExecStart=/usr/local/bin/docker compose -f $REPO_DIR/$COMPOSE_FILE -f $REPO_DIR/$COMPOSE_OVERRIDE up -d
ExecStop=/usr/local/bin/docker compose -f $REPO_DIR/$COMPOSE_FILE -f $REPO_DIR/$COMPOSE_OVERRIDE down
ExecStartPost=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8001 > /tmp/cloudflared.log 2>&1 &
Restart=on-failure
RestartSec=30
User=$USER
Environment=HF_TOKEN=$HF_TOKEN
Environment=ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable trg-watchdog.service
ok "systemd watchdog installed (sudo systemctl {start,status,stop} trg-watchdog)"

# ─── Summary ───────────────────────────────────────────────────────────
step "Summary"
echo ""
echo -e "  ${GREEN}✓ Docker stack is running${NC} (profile: $PROFILE)"
echo -e "  ${GREEN}✓ Agent API on http://localhost:8001${NC}"
echo -e "  ${GREEN}✓ PWA served at / by the same FastAPI${NC}"
echo ""
if [ -n "$URL" ]; then
  echo -e "  ${BOLD}PUBLIC URL (Cloudflare quick tunnel):${NC}"
  echo -e "  ${BLUE}${URL}${NC}"
  echo ""
  echo -e "  ${YELLOW}This URL is random and will change on the next VM restart.${NC}"
  echo -e "  ${YELLOW}For a persistent URL, see: https://github.com/barnymurt/trg-report/blob/main/infra/oracle/DEPLOY.md${NC}"
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
echo -e "  ${BOLD}Manage the stack:${NC}"
echo "    sudo systemctl status trg-watchdog      # current state"
echo "    sudo systemctl restart trg-watchdog     # restart everything"
echo "    cd $REPO_DIR && docker compose -f $COMPOSE_FILE -f $COMPOSE_OVERRIDE logs -f"
echo ""
ok "done"
