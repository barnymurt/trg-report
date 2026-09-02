#!/usr/bin/env pwsh
# deploy-all.ps1 — orchestrate the full HF Spaces + Cloudflare Pages deploy.
#
# Use this locally to push everything in one go (faster than waiting for
# GitHub Actions on a clean repo). Requires:
#   - HF_TOKEN                   (huggingface.co write token)
#   - CLOUDFLARE_API_TOKEN       (Cloudflare dashboard → API tokens)
#   - CLOUDFLARE_ACCOUNT_ID      (Cloudflare dashboard URL fragment)
#   - ANTHROPIC_API_KEY          (for the agent Space secret)
#
# Usage:
#   pwsh deploy/deploy-all.ps1                # deploy everything
#   pwsh deploy/deploy-all.ps1 -AgentOnly     # only the agent backend
#   pwsh deploy/deploy-all.ps1 -UploadOnly    # just upload, don't trigger build

[CmdletBinding()]
param(
    [switch]$AgentOnly,
    [switch]$UploadOnly,
    [switch]$Help,
)

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    exit 0
}

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot/..").Path

# ─── Preflight ─────────────────────────────────────────────────────────
Write-Host "==> Checking environment..." -ForegroundColor Cyan

function Require-Cmd($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "  MISSING: $name" -ForegroundColor Red
        exit 1
    }
    Write-Host "  OK: $name" -ForegroundColor Green
}

Require-Cmd python
Require-Cmd huggingface-cli

if (-not $env:HF_TOKEN) {
    Write-Host "  HF_TOKEN not set. Get one at https://huggingface.co/settings/tokens" -ForegroundColor Red
    exit 1
}

if (-not $AgentOnly -and -not $env:CLOUDFLARE_API_TOKEN) {
    Write-Host "  CLOUDFLARE_API_TOKEN not set (needed for PWA deploy). Skipping PWA." -ForegroundColor Yellow
    $skipCloudflare = $true
} else {
    $skipCloudflare = $AgentOnly
}

# ─── Login to HF ──────────────────────────────────────────────────────
Write-Host "`n==> Logging in to Hugging Face..." -ForegroundColor Cyan
huggingface-cli login --token $env:HF_TOKEN | Out-Null
Write-Host "  OK" -ForegroundColor Green

# ─── Upload Spaces ────────────────────────────────────────────────────
function Push-Space {
    param([string]$Name, [string]$SourceDir, [bool]$Private)
    Write-Host "`n==> Uploading $Name..." -ForegroundColor Cyan

    $tmp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP "trg-space-$Name") -Force

    # Copy the space files
    Copy-Item -Recurse -Force "$RepoRoot/$SourceDir/*" $tmp/

    # If the source Dockerfile references monorepo paths, flatten them
    Get-ChildItem $tmp/Dockerfile -ErrorAction SilentlyContinue | ForEach-Object {
        $content = Get-Content $_.FullName -Raw
        $content = $content -replace 'COPY apps/agent/pyproject.toml ./', 'COPY pyproject.toml ./'
        $content = $content -replace 'COPY apps/agent/src/ ./src/', 'COPY src/ ./src/'
        $content = $content -replace 'COPY deploy/hf_spaces/trg-voice/server.py', 'COPY server.py'
        $content = $content -replace 'COPY deploy/hf_spaces/trg-voice/start.sh', 'COPY start.sh'
        Set-Content -Path $_.FullName -Value $content
    }

    # For trg-agent: also need the agent source code
    if ($Name -eq "trg-agent") {
        Copy-Item -Recurse -Force "$RepoRoot/apps/agent/src" $tmp/src
        Copy-Item -Force "$RepoRoot/apps/agent/pyproject.toml" $tmp/
    }

    Push-Location $tmp
    try {
        $visibility = if ($Private) { "private" } else { "public" }
        # Ensure Space exists
        huggingface-cli repo create $Name --type space --space-sdk docker --$visibility 2>$null
        huggingface-cli upload --repo-type space --$visibility "barnymurt/$Name" . . | Out-Null
        Write-Host "  Uploaded $Name" -ForegroundColor Green
    } finally {
        Pop-Location
        Remove-Item -Recurse -Force $tmp
    }
}

if (-not $UploadOnly) {
    Push-Space -Name "trg-agent"      -SourceDir "deploy/hf_spaces/trg-agent"      -Private $true
    Push-Space -Name "trg-voice"      -SourceDir "deploy/hf_spaces/trg-voice"      -Private $false
    Push-Space -Name "trg-embeddings" -SourceDir "deploy/hf_spaces/trg-embeddings" -Private $false
} else {
    Write-Host "UploadOnly: skipping upload" -ForegroundColor Yellow
}

# ─── Set agent secrets ────────────────────────────────────────────────
Write-Host "`n==> Setting trg-agent secrets..." -ForegroundColor Cyan
if ($env:ANTHROPIC_API_KEY) {
    $env:HF_TOKEN | Out-Null  # already logged in
    python -c "
import os
from huggingface_hub import HfApi
api = HfApi(token=os.environ['HF_TOKEN'])
api.add_space_secret(repo_id='barnymurt/trg-agent', key='ANTHROPIC_API_KEY', value=os.environ['ANTHROPIC_API_KEY'])
print('  Set ANTHROPIC_API_KEY')
" 2>&1 | Where-Object { $_ -match 'Set|error' } | ForEach-Object { Write-Host "  $_" -ForegroundColor Green }
} else {
    Write-Host "  ANTHROPIC_API_KEY not set — skipping. Add it manually in Space Settings." -ForegroundColor Yellow
}

# ─── Cloudflare Pages ────────────────────────────────────────────────
if (-not $skipCloudflare) {
    Write-Host "`n==> Deploying PWA to Cloudflare Pages..." -ForegroundColor Cyan
    Require-Cmd wrangler

    $env:CLOUDFLARE_API_TOKEN | Out-Null
    $env:CLOUDFLARE_ACCOUNT_ID | Out-Null

    Push-Location $RepoRoot
    try {
        # Build the static export
        pnpm --filter @trg/web exec next build 2>&1 | Tee-Object -FilePath "C:\Users\bmurt\AppData\Local\Temp\cf-build.log" | Select-Object -Last 5 | Write-Host

        # Deploy
        wrangler pages deploy apps/web/out --project-name trg-web 2>&1 | Tee-Object -FilePath "C:\Users\bmurt\AppData\Local\Temp\cf-deploy.log" | Select-Object -Last 10 | Write-Host
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n==> Skipping Cloudflare deploy (no token, or -AgentOnly)" -ForegroundColor Yellow
}

Write-Host "`n==> Done." -ForegroundColor Green
Write-Host "Watch builds at:"
Write-Host "  - https://huggingface.co/spaces/barnymurt/trg-agent/logs"
Write-Host "  - https://huggingface.co/spaces/barnymurt/trg-voice/logs"
Write-Host "  - https://huggingface.co/spaces/barnymurt/trg-embeddings/logs"
Write-Host "  - https://dash.cloudflare.com/?to=/:account/pages/trg-web"
