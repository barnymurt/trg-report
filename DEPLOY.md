# TRG — Deployment Guide

This guide gets TRG live on **Hugging Face Spaces** (backend + voice + embeddings) and **Cloudflare Pages** (PWA). Free tier for all but one; private Space requires **Hugging Face Pro ($2/mo)**.

## Architecture (live)

```
                  ┌─────────────────────────────────────────────────────────────┐
                  │                    Cloudflare Pages (free)                   │
                  │                PWA: trg-web.pages.dev                         │
                  │   (Next.js static export — installed on phone home screen)   │
                  └─────────────────────────────┬───────────────────────────────┘
                                                │ HTTPS, JSON over fetch
                                                ▼
                  ┌─────────────────────────────────────────────────────────────┐
                  │             Hugging Face Space: barnymurt/trg-agent          │
                  │       (private, $2/mo HF Pro) — FastAPI + Qdrant + SmolLM2    │
                  └────────┬────────────────┬─────────────────┬───────────────────┘
                           │                │                 │
                           ▼                ▼                 ▼
              ┌─────────────────┐ ┌──────────────────┐ ┌────────────────────┐
              │ trg-voice       │ │ trg-embeddings   │ │ Anthropic API      │
              │ Whisper + Kokoro│ │ TEI bge-small    │ │ Claude (Haiku/     │
              │ (public, free)  │ │ (public, free)   │ │  Sonnet / Thinking)│
              └─────────────────┘ └──────────────────┘ └────────────────────┘
```

All Spaces run on Hugging Face's free tier; only `trg-agent` is private (Pro needed for private Spaces).

## One-time setup (~30 min)

### 1. Hugging Face account + Pro

1. Sign up at <https://huggingface.co/join>
2. Subscribe to Pro at <https://huggingface.co/settings/billing> ($2/mo)
3. Create a write token at <https://huggingface.co/settings/tokens> with `write` scope
4. Save the token — you'll add it to GitHub Secrets as `HF_TOKEN`

### 2. Cloudflare account

1. Sign up at <https://dash.cloudflare.com/sign-up> (free)
2. Get your Account ID from the dashboard URL: `https://dash.cloudflare.com/<ACCOUNT_ID>/...`
3. Create an API token at <https://dash.cloudflare.com/profile/api-tokens> with `Cloudflare Pages: Edit` template
4. Save both — add to GitHub Secrets as `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`

### 3. Anthropic API key

1. Get one at <https://console.anthropic.com/settings/keys>
2. Save it — add as a Space secret (see step 5)

### 4. Push to GitHub

```bash
git push origin main
```

The repo is already at <https://github.com/barnymurt/trg-report>. Add the secrets at <https://github.com/barnymurt/trg-report/settings/secrets/actions>:
- `HF_TOKEN`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

### 5. Create the three Hugging Face Spaces

You can create them via the UI or via the CLI. The CLI is faster:

```bash
# Install the HF CLI (already done if you used huggingface-cli earlier)
pip install -U "huggingface_hub[cli]"

# Login
huggingface-cli login   # paste your HF_TOKEN

# Create the three Spaces
huggingface-cli repo create trg-agent      --type space --space-sdk docker --private
huggingface-cli repo create trg-voice      --type space --space-sdk docker --public
huggingface-cli repo create trg-embeddings --type space --space-sdk docker --public
```

### 6. Add the Anthropic API key to `trg-agent`

1. Go to <https://huggingface.co/spaces/barnymurt/trg-agent/settings> → Variables and secrets
2. Add a **secret**: `ANTHROPIC_API_KEY` = `sk-ant-...`
3. (Optional but useful) Add variables:
   - `TRG_DEMO_MODE` = `false` (use real Claude; `true` for canned responses)
   - `TEI_URL` = `https://barnymurt-trg-embeddings.hf.space`
   - `WHISPER_URL` = `https://barnymurt-trg-voice.hf.space`
   - `KOKORO_URL` = `https://barnymurt-trg-voice.hf.space`

### 7. Trigger the deploy workflows

The first deploy happens automatically on push to `main` (because `.github/workflows/deploy-hf-spaces.yml` watches `deploy/hf_spaces/**`). But since you just created the Spaces, the first sync hasn't happened yet. Trigger manually:

<https://github.com/barnymurt/trg-report/actions/workflows/deploy-hf-spaces.yml> → Run workflow → choose `all`.

The same applies to the PWA: <https://github.com/barnymurt/trg-report/actions/workflows/deploy-pwa.yml> → Run workflow.

### 8. Wait for builds

HF Spaces take 5–10 min for first build (model downloads). Watch at:
- <https://huggingface.co/spaces/barnymurt/trg-agent/logs>
- <https://huggingface.co/spaces/barnymurt/trg-voice/logs>
- <https://huggingface.co/spaces/barnymurt/trg-embeddings/logs>

Cloudflare Pages: <https://dash.cloudflare.com/?to=/:account/pages/trg-web`

### 9. Smoke test

Once everything is up:
```bash
curl https://barnymurt-trg-agent.hf.space/health
curl https://barnymurt-trg-embeddings.hf.space/health
curl https://barnymurt-trg-voice.hf.space/health
```

Open the PWA URL (Cloudflare will print it after the first deploy — typically `https://trg-web.pages.dev`).

## Costs

| Item | Cost |
|---|---|
| Hugging Face Pro (private `trg-agent`) | $2/mo |
| `trg-voice` Space (public, free) | $0 |
| `trg-embeddings` Space (public, free) | $0 |
| Cloudflare Pages | $0 |
| Anthropic API (Haiku-heavy use) | a few $/mo |
| **Total** | **~$5/mo** |

## Daily use

After deploy, the system runs 24/7. The professor opens the PWA on her phone, talks, and approves actions. The agent handles the rest.

To update the agents / UI:
```bash
# Make changes locally
git commit -am "feat: ..."
git push
# Workflows auto-deploy on push to main.
```

To rotate the Anthropic API key:
1. <https://console.anthropic.com/settings/keys> → Revoke old, create new
2. <https://huggingface.co/spaces/barnymurt/trg-agent/settings> → update the secret
3. The Space restarts automatically with the new key

## What if a Space sleeps?

HF free-tier CPU Spaces sleep after 48 hours of inactivity. `trg-voice` and `trg-embeddings` will wake on the next request. The professor won't notice anything except a 5–10 second cold-start the first time she uses voice after a quiet day.

If you want guaranteed no-sleep, upgrade those Spaces to Pro too ($9/mo each). Probably not worth it.

## Custom domain (optional)

If you register a domain (e.g. via Cloudflare Registrar, ~€10/yr):

1. Cloudflare Pages: Custom domains → add `trg.example.com`
2. HF Space: Settings → Direct URL isn't customisable but the subdomain is `barnymurt-trg-agent.hf.space`. For a custom backend domain, point a CNAME at the Space via Cloudflare for SaaS.

For now, the default URLs work fine.

## Backup

HF Spaces persist `/data` to a volume. Backups happen via the cron in the agent (writes to `/data/backups/`). To download a backup:

```python
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id="barnymurt/trg-agent",
    filename="backups/2026-09-02.tar.gz",
    repo_type="space",
    local_dir="./backup",
)
```

For full disaster recovery, set up a GitHub Action that runs daily and uploads the latest snapshot to a private HF Dataset (`barnymurt/trg-agent-backups`).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `trg-agent` Space shows "Application startup failed" | Anthropic API key missing or invalid | Add `ANTHROPIC_API_KEY` in Space Settings → Variables and secrets |
| PWA loads but chat says "Couldn't reach agent backend" | Agent Space still building, or wrong URL | Wait for build; check `NEXT_PUBLIC_API_URL` |
| Voice button does nothing | `trg-voice` still building or model download failed | Check logs; first request can take 30s while Whisper model loads |
| Embeddings 503 | `trg-embeddings` not deployed yet | Trigger deploy-hf-spaces workflow with `trg-embeddings` |
| Action approve shows "Approval failed: HTTP 401" | The Space secret `ANTHROPIC_API_KEY` is missing | Add it (see step 6) |

See `infra/SETUP.md` for the local-dev counterpart.
