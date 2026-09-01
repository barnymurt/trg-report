#!/usr/bin/env bash
# preflight.sh — diagnostics for the TRG Agent Team local stack.
#
# Verifies the host can actually run the stack before we attempt to start
# anything. Each check prints PASS / WARN / FAIL with a one-line fix.
#
# Run from the repo root:
#   bash infra/scripts/preflight.sh
#
# Exit code:
#   0   all critical checks pass (warnings allowed)
#   1   one or more critical checks failed
#
# Use --strict to also fail on warnings.

set -u

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
NC=$'\033[0m'

STRICT=0
if [ "${1:-}" = "--strict" ]; then
  STRICT=1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OS="$(uname -s)"

REQUIRED_PORTS=(6333 6334 8080 8081 8082 8000 8001 8880 9000 5001)
MIN_RAM_GB=16
MIN_DISK_GB=30

# Counters
PASS=0
WARN=0
FAIL=0

# ─── Pretty printers ────────────────────────────────────────────────────

print_header() {
  printf "\n${BOLD}${BLUE}── %s ──${NC}\n" "$1"
}

pass() { printf "  ${GREEN}✓ PASS${NC}  %s\n" "$1"; PASS=$((PASS+1)); }
warn() { printf "  ${YELLOW}⚠ WARN${NC}  %s\n      ${YELLOW}→${NC} %s\n" "$1" "$2"; WARN=$((WARN+1)); }
fail() { printf "  ${RED}✗ FAIL${NC}  %s\n      ${RED}→${NC} %s\n" "$1" "$2"; FAIL=$((FAIL+1)); }

section() { printf "\n${BOLD}%s${NC}\n" "$1"; }

# ─── 1. Docker ───────────────────────────────────────────────────────────

print_header "Docker"

if command -v docker >/dev/null 2>&1; then
  DOCKER_VERSION="$(docker --version 2>/dev/null || echo 'unknown')"
  pass "Docker CLI installed ($DOCKER_VERSION)"
else
  fail "Docker CLI not installed" "Install Docker Desktop from https://docker.com/products/docker-desktop/ and restart your shell."
fi

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    SERVER_VERSION="$(docker info --format '{{.ServerVersion}}' 2>/dev/null || echo 'unknown')"
    pass "Docker daemon reachable (server $SERVER_VERSION)"
  else
    if [ "$OS" = "Darwin" ]; then
      fail "Docker daemon not reachable" "Open Docker Desktop from Applications — wait for the whale icon to stop animating, then re-run this script."
    elif [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* || "$OS" == "Windows"* ]]; then
      fail "Docker daemon not reachable" "Start Docker Desktop from the Start menu, or run 'Docker Desktop.exe' from C:\\Program Files\\Docker\\Docker. Wait for the tray icon to stop animating, then re-run this script."
    else
      fail "Docker daemon not reachable" "Run 'sudo systemctl start docker' (or your distro's equivalent), then re-run this script."
    fi
  fi
fi

# Compose plugin
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  pass "Docker Compose plugin present ($(docker compose version --short 2>/dev/null))"
else
  fail "Docker Compose plugin missing" "Update Docker Desktop — the v2 plugin is bundled. Older Docker Engine may need 'docker-compose-plugin' installed."
fi

# WSL2 check (Windows)
if [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* || "$OS" == "Windows"* ]]; then
  if command -v wsl >/dev/null 2>&1; then
    if wsl --status >/dev/null 2>&1; then
      WSL_VER="$(wsl --status 2>&1 | grep -i 'default version' | head -n1 || echo 'unknown')"
      pass "WSL present ($WSL_VER)"
    else
      warn "WSL present but may not be set up" "Run 'wsl --install' in an Administrator PowerShell, then restart."
    fi
  else
    warn "WSL not detected" "Docker Desktop on Windows requires WSL2. Run 'wsl --install' in an Administrator PowerShell and restart."
  fi
fi

# ─── 2. Resources ───────────────────────────────────────────────────────

print_header "Host resources"

# RAM (rough cross-platform estimate)
get_ram_gb() {
  if [ "$OS" = "Darwin" ]; then
    echo $(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
  elif [ -f /proc/meminfo ]; then
    awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo
  elif [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* || "$OS" == "Windows"* ]]; then
    powershell -NoProfile -Command "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB" 2>/dev/null | awk '{printf "%d", $1}'
  else
    echo 0
  fi
}

RAM_GB="$(get_ram_gb)"
if [ "$RAM_GB" -ge "$MIN_RAM_GB" ]; then
  pass "RAM: ${RAM_GB} GB (>= ${MIN_RAM_GB} GB recommended)"
else
  if [ "$RAM_GB" -eq 0 ]; then
    warn "Could not detect RAM" "Manually verify your machine has at least ${MIN_RAM_GB} GB. The stack runs with several ML models."
  else
    fail "RAM: ${RAM_GB} GB (< ${MIN_RAM_GB} GB required)" "The full stack needs ${MIN_RAM_GB}+ GB. Try running with FEWER services (drop tei-multilingual, docling, reranker) or use 'install-native.sh' to run only what you need."
  fi
fi

# Disk
get_disk_free_gb() {
  case "$OS" in
    Darwin|Linux) df -g . 2>/dev/null | awk 'NR==2 {print $4}' ;;
    *) df -BG . 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}' ;;
  esac
}

DISK_GB="$(get_disk_free_gb 2>/dev/null || echo 0)"
if [ -n "$DISK_GB" ] && [ "$DISK_GB" -ge "$MIN_DISK_GB" ] 2>/dev/null; then
  pass "Disk free: ${DISK_GB} GB (>= ${MIN_DISK_GB} GB recommended)"
else
  if [ -z "$DISK_GB" ] || [ "$DISK_GB" -eq 0 ]; then
    warn "Could not detect free disk" "Manually verify you have ${MIN_DISK_GB}+ GB free. Model weights are large (~10 GB)."
  else
    fail "Disk free: ${DISK_GB} GB (< ${MIN_DISK_GB} GB required)" "Free up disk space (models are large), or change the volumes in docker-compose.yml to a larger drive."
  fi
fi

# ─── 3. Ports ────────────────────────────────────────────────────────────

print_header "Ports"

check_port() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
      return 1  # in use
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -tln 2>/dev/null | grep -q ":$port "; then
      return 1
    fi
  elif [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* || "$OS" == "Windows"* ]]; then
    if powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue" 2>/dev/null | grep -q "$port"; then
      return 1
    fi
  fi
  return 0
}

PORT_FAIL=0
for port in "${REQUIRED_PORTS[@]}"; do
  if check_port "$port"; then
    :  # free, no per-port output to keep noise low
  else
    fail "Port $port already in use" "Stop whatever is using it (or change the published port in docker-compose.yml and infra/caddy/Caddyfile)."
    PORT_FAIL=$((PORT_FAIL+1))
  fi
done

if [ "$PORT_FAIL" -eq 0 ]; then
  pass "All ${#REQUIRED_PORTS[@]} required ports are free"
fi

# ─── 4. Network ─────────────────────────────────────────────────────────

print_header "Network"

if curl -sf -o /dev/null --max-time 5 https://huggingface.co/; then
  pass "huggingface.co reachable"
else
  fail "huggingface.co unreachable" "Check your internet connection, proxy settings, or firewall. Model downloads require this."
fi

if curl -sf -o /dev/null --max-time 5 https://ghcr.io/; then
  pass "ghcr.io reachable (Docker image registry)"
else
  fail "ghcr.io unreachable" "Docker image pulls require this. Check your connection or configure a Docker registry mirror."
fi

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  pass "ANTHROPIC_API_KEY set in environment"
else
  if [ -f "$REPO_ROOT/.env" ] && grep -q '^ANTHROPIC_API_KEY=' "$REPO_ROOT/.env"; then
    pass "ANTHROPIC_API_KEY set in .env"
  else
    fail "ANTHROPIC_API_KEY not set" "Add ANTHROPIC_API_KEY=sk-ant-... to your .env file (copy from .env.example). The Claude LLM requires it."
  fi
fi

# ─── 5. Compose file ────────────────────────────────────────────────────

print_header "Compose file"

if [ -f "$REPO_ROOT/.env" ]; then
  pass ".env file present"
else
  if [ -f "$REPO_ROOT/.env.example" ]; then
    warn ".env not found" "Copy .env.example to .env and fill in ANTHROPIC_API_KEY. (cp .env.example .env)"
  else
    fail ".env.example missing" "Re-clone the repository."
  fi
fi

if [ -f "$REPO_ROOT/infra/docker-compose.yml" ]; then
  pass "infra/docker-compose.yml present"
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if docker compose -f "$REPO_ROOT/infra/docker-compose.yml" config >/dev/null 2>&1; then
      pass "docker-compose.yml is valid"
    else
      fail "docker-compose.yml has errors" "Run 'docker compose -f infra/docker-compose.yml config' to see the issue."
    fi
  fi
else
  fail "infra/docker-compose.yml missing" "Re-clone the repository."
fi

# ─── 6. Power settings ──────────────────────────────────────────────────

print_header "Host behaviour"

if [ "$OS" = "Darwin" ]; then
  PMSCUR="$(pmset -g 2>/dev/null | grep -E 'sleep|display' | head -n 2 || echo unknown)"
  pass "macOS power settings: ${PMSCUR}"
elif [ -f /etc/systemd/logind.conf ]; then
  if grep -qE '^HandleLidSwitch=ignore' /etc/systemd/logind.conf 2>/dev/null; then
    pass "systemd configured to ignore lid switch"
  else
    warn "systemd not configured for always-on" "Run infra/scripts/setup-power.sh to keep the laptop awake on AC power."
  fi
elif [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* || "$OS" == "Windows"* ]]; then
  STANDBY=$(powershell -NoProfile -Command "(powercfg /q SCHEME_CURRENT | Select-String -Pattern 'STANDBYIDLE' | Select-Object -First 1)" 2>/dev/null || echo unknown)
  pass "Windows power settings: ${STANDBY}"
fi

# ─── Summary ────────────────────────────────────────────────────────────

section ""
printf "${BOLD}Summary${NC}\n"
printf "  ${GREEN}PASS${NC}: %d\n" "$PASS"
printf "  ${YELLOW}WARN${NC}: %d\n" "$WARN"
printf "  ${RED}FAIL${NC}: %d\n" "$FAIL"

if [ "$FAIL" -eq 0 ]; then
  if [ "$STRICT" -eq 1 ] && [ "$WARN" -gt 0 ]; then
    section "${YELLOW}Strict mode: warnings present, but no failures.${NC}"
    exit 1
  fi
  section "${GREEN}All critical checks passed. Run 'pnpm infra:up' to start the stack.${NC}"
  exit 0
else
  section "${RED}Fix the failures above and re-run preflight.sh.${NC}"
  exit 1
fi
