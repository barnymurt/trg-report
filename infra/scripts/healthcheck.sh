#!/usr/bin/env bash
# Healthcheck — pings the local services and prints a status summary.
# Used by external monitoring (UptimeRobot / Healthchecks.io) via HTTP
# or run manually to verify the stack is healthy.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${url}" || echo "000")
  if [ "${code}" = "200" ]; then
    printf "  ${GREEN}✓${NC} %-22s %s\n" "${name}" "${url}"
    return 0
  else
    printf "  ${RED}✗${NC} %-22s %s (HTTP %s)\n" "${name}" "${url}" "${code}"
    return 1
  fi
}

echo "TRG Agent Team — healthcheck"
echo "─────────────────────────────"
FAIL=0

check "Qdrant"          "http://localhost:6333/health"     || FAIL=1
check "TEI embeddings"  "http://localhost:8080/health"     || FAIL=1
check "TEI multilingual" "http://localhost:8082/health"    || FAIL=1
check "TEI reranker"    "http://localhost:8081/health"     || FAIL=1
check "Whisper"         "http://localhost:9000/"           || FAIL=1
check "Kokoro TTS"      "http://localhost:8880/v1/audio/voices" || FAIL=1
check "SmolLM2"         "http://localhost:8000/health"     || FAIL=1
check "Agent backend"   "http://localhost:8001/health"     || FAIL=1

echo ""
if [ "${FAIL}" -eq 0 ]; then
  printf "${GREEN}All services healthy.${NC}\n"
  exit 0
else
  printf "${RED}One or more services are unhealthy.${NC}\n"
  exit 1
fi
