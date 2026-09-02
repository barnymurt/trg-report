#!/usr/bin/env pwsh
# start-web.ps1 — launch the TRG PWA (Next.js) with auto-restart + logging.
#
# Usage:
#   pwsh infra/scripts/start-web.ps1
#   pwsh infra/scripts/start-web.ps1 -Stop
#   pwsh infra/scripts/start-web.ps1 -Status

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot/../..").Path
$DataDir  = Join-Path $RepoRoot "data"
$PidFile  = Join-Path $DataDir ".web.pid"
$LogFile  = Join-Path $DataDir ".web.log"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

if ($Stop) {
    if (Test-Path $PidFile) {
        $pidVal = Get-Content $PidFile -Raw -ErrorAction SilentlyContinue
        if ($pidVal -and $pidVal.Trim() -match '^\d+$') {
            Stop-Process -Id ([int]$pidVal.Trim()) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped."
    exit 0
}

if ($Status) {
    if (Test-Path $PidFile) {
        $pidVal = Get-Content $PidFile -Raw
        $proc = Get-Process -Id ([int]$pidVal.Trim()) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "PWA running: PID $pidVal, started $($proc.StartTime)"
        } else {
            Write-Host "Stale PID file."
        }
    } else {
        Write-Host "No PID file. PWA not running."
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue
    if ($listener) { Write-Host "Port 3000: LISTENING" } else { Write-Host "Port 3000: free" }
    exit 0
}

# Kill anything on port 3000
Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "Killing stale process on port 3000: PID $($_.OwningProcess)"
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Milliseconds 500

# Load .env into environment vars so Next.js / the agent see them
if (Test-Path "$RepoRoot/.env") {
    Get-Content "$RepoRoot/.env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        if ($_ -match '^([A-Z_][A-Z0-9_]*)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
        }
    }
}

Write-Host "Launching PWA (logging to $LogFile)…"
$cmdLine = "cd /d `"$RepoRoot`" && pnpm --filter @trg/web dev >> `"$LogFile`" 2>&1"
$proc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "start", "/B", "cmd.exe", "/c", $cmdLine `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Launched (parent PID $($proc.Id))"

# Wait for port to come up + record the actual node PID
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    $listener = Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue
    if ($listener) {
        Set-Content -Path $PidFile -Value $listener.OwningProcess -Force
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] PWA healthy on port 3000 (PID $($listener.OwningProcess))"
        exit 0
    }
}

Write-Host "PWA failed to start within 60s. See $LogFile"
exit 1
