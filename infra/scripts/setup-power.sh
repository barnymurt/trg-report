#!/usr/bin/env bash
# setup-power.sh — configure the laptop so the agent backend stays
# reachable from the mobile PWA when the user is out of the house.
#
# Two things:
#   1. Power settings: keep the laptop awake on AC power.
#   2. Docker autostart: ensure Docker Desktop starts on boot.

set -euo pipefail

OS="$(uname -s)"
echo "Detected OS: ${OS}"

# ─── 1. Power settings ─────────────────────────────────────────────────

configure_power() {
  case "${OS}" in
    Darwin)
      echo "Configuring macOS power settings (AC power only)…"
      sudo pmset -c displaysleep 0
      sudo pmset -c sleep 0
      sudo pmset -c powernap 0
      sudo pmset -c womp 1   # Wake on LAN — useful if laptop does sleep
      echo "Done. Verify with: pmset -g | grep -E '(sleep|display)'"
      ;;

    Linux)
      echo "Configuring systemd-logind…"
      sudo sed -i 's/^#HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
      sudo sed -i 's/^#HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
      sudo sed -i 's/^#IdleAction=.*/IdleAction=ignore/' /etc/systemd/logind.conf
      sudo systemctl restart systemd-logind
      echo "Done. Lid close no longer suspends; idle no longer suspends."
      ;;

    MINGW*|MSYS*|CYGWIN*|Windows*)
      echo "Configuring Windows power settings (AC power only)…"
      powershell -NoProfile -Command "
        powercfg -change -monitor-timeout-ac 0;
        powercfg -change -standby-timeout-ac 0;
        powercfg -change -hibernate-timeout-ac 0;
        powercfg -change -monitor-timeout-dc 5;
        powercfg -change -standby-timeout-dc 15;
        Write-Host 'Sleep + hibernate disabled on AC; battery defaults preserved.'
      "
      ;;

    *)
      echo "Unknown OS — please configure manually so the laptop stays awake on AC power."
      return 1
      ;;
  esac
}

# ─── 2. Docker autostart ────────────────────────────────────────────────

configure_docker_autostart() {
  case "${OS}" in
    Darwin)
      echo "Configuring Docker Desktop to start on login (macOS)…"
      # Use launchctl to register Docker as a login item
      osascript -e 'tell application "System Events" to make login item at end with properties {path:"/Applications/Docker.app", hidden:true}' \
        2>/dev/null || warn "Couldn't register Docker as login item; you can do it manually in System Settings → General → Login Items"
      echo "Done."
      ;;

    Linux)
      echo "Configuring Docker to start on boot (Linux systemd)…"
      if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl enable docker
        sudo systemctl start docker
        echo "Done. sudo systemctl status docker"
      else
        warn "systemctl not available; configure manually for your distro."
      fi
      ;;

    MINGW*|MSYS*|CYGWIN*|Windows*)
      echo "Configuring Docker Desktop autostart on Windows…"
      # Docker Desktop has a setting 'Start Docker Desktop when you sign in'.
      # It's stored in the user's registry under
      # HKCU\Software\Docker Inc.\Docker\settings.
      reg add "HKCU\Software\Docker Inc.\Docker\settings" \
        /v autoStart /t REG_SZ /d "true" /f 2>/dev/null \
        || warn "Couldn't write registry key; enable 'Start Docker Desktop when you sign in' in Docker Desktop → Settings → General."
      echo "Done (or warned)."
      ;;

    *)
      warn "Unknown OS; configure Docker autostart manually."
      ;;
  esac
}

warn() { printf "  \033[1;33m⚠\033[0m %s\n" "$1"; }

configure_power
echo ""
configure_docker_autostart
echo ""
echo "Once configured, the laptop will stay on whenever plugged in,"
echo "Docker will start automatically, and the Cloudflare Tunnel will keep"
echo "the agent backend reachable from your phone anywhere."
