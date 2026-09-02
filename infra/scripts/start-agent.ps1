#!/usr/bin/env pwsh
# start-agent.ps1 — launch the TRG agent backend with auto-restart + logging.
#
# Usage:
#   pwsh infra/scripts/start-agent.ps1              # start with watchdog
#   pwsh infra/scripts/start-agent.ps1 -Once        # start without watchdog
#   pwsh infra/scripts/start-agent.ps1 -Stop        # stop the running instance
#   pwsh infra/scripts/start-agent.ps1 -Status      # print status
#
# Writes:
#   data/.agent.pid    — current PID
#   data/.agent.log    — combined stdout + stderr
#
# The watchdog restarts the process up to 5 times in 60 seconds if it dies.

[CmdletBinding()]
param(
    [switch]$Once,
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot/../..").Path
$DataDir  = Join-Path $RepoRoot "data"
$PidFile  = Join-Path $DataDir ".agent.pid"
$LogFile  = Join-Path $DataDir ".agent.log"

# Ensure data dir exists
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

# ─── Stop ──────────────────────────────────────────────────────────────
if ($Stop) {
    if (Test-Path $PidFile) {
        $pidVal = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
        if ($pidVal -and $pidVal.Trim() -match '^\d+$') {
            $proc = Get-Process -Id ([int]$pidVal.Trim()) -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "Stopping agent (PID $pidVal)…"
                Stop-Process -Id ([int]$pidVal.Trim()) -Force
                # Also kill any child python processes
                Get-CimInstance Win32_Process -Filter "ParentProcessId=$pidVal" -ErrorAction SilentlyContinue |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                Start-Sleep -Seconds 1
            }
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    # Also kill anything on port 8001
    Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue |
        ForEach-Object {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    Write-Host "Stopped."
    exit 0
}

# ─── Status ────────────────────────────────────────────────────────────
if ($Status) {
    if (Test-Path $PidFile) {
        $pidVal = Get-Content $PidFile -Raw
        $proc = Get-Process -Id ([int]$pidVal.Trim()) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Agent running: PID $pidVal, started $($proc.StartTime)"
        } else {
            Write-Host "Stale PID file. Process not running."
        }
    } else {
        Write-Host "No PID file. Agent not running."
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "Port 8001: LISTENING"
    } else {
        Write-Host "Port 8001: free"
    }
    exit 0
}

# ─── Start ────────────────────────────────────────────────────────────

function Test-AgentHealthy {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8001/health" -TimeoutSec 2
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Kill-Port8001 {
    Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "Killing stale process on port 8001: PID $($_.OwningProcess)"
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 500
}

function Launch-Agent {
    param([string]$LogPath)
    Kill-Port8001
    Write-Host "Launching agent (logging to $LogPath)…"

    # Build a `set VAR=val &&` prefix from the .env file so pydantic-settings
    # picks them up via real environment variables (more reliable than env_file).
    $envVars = @()
    if (Test-Path "$RepoRoot/.env") {
        Get-Content "$RepoRoot/.env" | ForEach-Object {
            if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
            if ($_ -match '^([A-Z_][A-Z0-9_]*)=(.*)$') {
                $name = $Matches[1]
                $val  = $Matches[2]
                $envVars += "set $name=$val"
            }
        }
    }
    $envPrefix = ($envVars -join "&& ")
    if ($envPrefix) { $envPrefix = "$envPrefix&& " }

    $Env:PYTHONPATH = "$RepoRoot/apps/agent/src"
    $cmdLine = "${envPrefix}set PYTHONPATH=$Env:PYTHONPATH&& cd /d `"$RepoRoot/apps/agent`" && python -m uvicorn trg.main:app --host 127.0.0.1 --port 8001 --log-level info --timeout-keep-alive 30 >> `"$LogPath`" 2>&1"

    $proc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "start", "/B", "cmd.exe", "/c", $cmdLine `
        -WindowStyle Hidden `
        -PassThru

    if ($proc) {
        Write-Host "Launched (parent PID $($proc.Id))"
    }
    return $proc
}

# Clean any prior log
if (Test-Path $LogFile) { Remove-Item $LogFile -Force }

if ($Once) {
    Launch-Agent -LogPath $LogFile
    Write-Host "Started once (no watchdog). Use -Status to check, -Stop to kill."
    exit 0
}

# ─── Watchdog loop ─────────────────────────────────────────────────────
Write-Host "Starting agent with watchdog (Ctrl+C to stop)…"
$maxRestartsInWindow = 5
$windowSec = 60
$restartTimes = New-Object System.Collections.Generic.List[DateTime]

while ($true) {
    Launch-Agent -LogPath $LogFile | Out-Null

    # Wait for startup, polling health
    $started = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-AgentHealthy) {
            # Find and record the python PID
            $listener = Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue
            if ($listener) {
                Set-Content -Path $PidFile -Value $listener.OwningProcess -Force
            }
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Agent healthy on port 8001"
            $started = $true
            break
        }
    }

    if (-not $started) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Agent failed to become healthy within 30s. See $LogFile"
        # Throttle restarts
        $now = Get-Date
        $restartTimes.Add($now) | Out-Null
        $restartTimes = [System.Collections.Generic.List[DateTime]]($restartTimes | Where-Object { ($now - $_).TotalSeconds -lt $windowSec })
        if ($restartTimes.Count -gt $maxRestartsInWindow) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] FATAL: $maxRestartsInWindow restarts in ${windowSec}s. Bailing out."
            exit 1
        }
        continue
    }

    # Reset restart counter on healthy start
    $restartTimes.Clear()

    # Wait for the process to die (poll)
    while ($true) {
        Start-Sleep -Seconds 5
        if (-not (Test-AgentHealthy)) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Agent stopped responding. Restarting…"
            break
        }
    }
}
