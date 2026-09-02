# TRG — Deployment Guide

The simplest, cheapest "go live" path: **one Hugging Face Space** that serves the agent API **and** the PWA from a single URL. Two companion Spaces for voice + embeddings.

## What the professor gets

A single URL she bookmarkes on her phone home screen. She talks to it, swipes to approve actions, and Claude handles the rest. No laptop. No Docker. No tech support.

**Default URL after deploy:** `https://barnymurt-trg-agent.hf.space`
*The Space name `trg-agent` becomes `barnymurt-trg-agent.hf.space` on Hugging Face.*

## Cost summary

| Component | Plan | Cost |
|---|---|---|
| `barnymurt/trg-agent` (private) | HF Pro | $9/mo |
| `barnymurt/trg-voice` (public) | HF Free | $0 |
| `barnymurt/trg-embeddings` (public) | HF Free | $0 |
| Anthropic API (Claude reasoning) | pay-as-you-go | ~$1–5/mo at her volume |
| **Total** | | **~$10–14/mo** |

**Free tier fallback:** deploy `trg-agent` as PUBLIC (no Pro needed), but the data is then world-readable. Fine for an empty demo, **not** for the professor's real data.

## Architecture

```
                  ┌─────────────────────────────────────────────────────────────┐
                  │    Hugging Face Space: barnymurt/trg-agent                  │
                  │       (Docker Space, private, $9/mo HF Pro)                  │
                  │   ┌───────────────────────────────────────────────────────┐ │
                  │   │                  FastAPI process                       │ │
                  │   │  ───────────────────────────────────────────────────  │ │
                  │   │  /chat, /actions/execute, /agents, /audit, ... (API)│ │
                  │   │  /              → serves the PWA (static export)    │ │
                  │   │  /setup         → first-run wizard                  │ │
                  │   └───────────────────────────────────────────────────────┘ │
                  │   + Qdrant binary (in-process)                                │
                  │   + SmolLM2 routing (or HF Inference)                        │
                  │   + /data persistent storage (audit, docs, agent specs)      │
                  └─────────┬──────────────────┬───────────────────────────────────┘
                            │                  │
              ┌─────────────┘                  └─────────────┐
              ▼                                              ▼
  ┌─────────────────────┐                      ┌─────────────────────────────┐
  │ trg-voice           │                      │ trg-embeddings             │
  │ Whisper + Kokoro    │                      │ TEI bge-small-en-v1.5      │
  │ /v1/audio/...       │                      │ /v1/embeddings             │
  │ public, free        │                      │ public, free                │
  └─────────────────────┘                      └─────────────────────────────┘
              │                                              │
              └──────────────────┬───────────────────────────┘
                                 ▼
                  ┌─────────────────────────────────────────────────────────────┐
                  │                  Anthropic API (Claude)                         │
                  │         pay-as-you-go: ~$0.25/MTok Haiku input                   │
                  └─────────────────────────────────────────────────────────────┘
```

**One URL serves everything.** The PWA is bundled into the same Docker image as the agent backend and served by FastAPI at `/`. The API is at `/chat`, `/agents`, `/actions/execute`, etc. — same origin, no CORS, works on mobile browsers without HTTPS warnings.

## One-time setup (~20 minutes)

### 1. Hugging Face Pro

1. Sign up at <https://huggingface.co/join>
2. Subscribe to Pro at <https://huggingface.co/settings/billing> ($9/mo)
3. Create a write token at <https://huggingface.co/settings/tokens> with `write` scope
4. Save the token as `HF_TOKEN`

### 2. Anthropic API key

1. Create one at <https://console.anthropic.com/settings/keys>
2. Save as `ANTHROPIC_API_KEY`

### 3. Create the three Spaces

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli login   # paste HF_TOKEN

huggingface-cli repo create trg-agent      --type space --space-sdk docker --private
huggingface-cli repo create trg-voice      --type space --space-sdk docker --public
huggingface-cli repo create trg-embeddings --type space --space-sdk docker --public
```

### 4. Push the code

Two options:

**(a) Automatic via GitHub Actions** (recommended)
1. Push this repo to GitHub (already done)
2. Add `HF_TOKEN` as a secret at <https://github.com/barnymurt/trg-report/settings/secrets/actions>
3. Trigger: <https://github.com/barnymurt/trg-report/actions/workflows/deploy-hf-spaces.yml> → Run workflow → `all`

**(b) Manual from your laptop**
```bash
# Build the PWA static export
cd apps/web && pnpm exec next build && cd ../..

# Stage the space contents
mkdir -p /tmp/space && cd /tmp/space
cp -r C:/Dev/TRG/deploy/hf_spaces/trg-agent/* .
cp -r C:/Dev/TRG/apps/agent/src ./src
cp C:/Dev/TRG/apps/agent/pyproject.toml .
cp -r C:/Dev/TRG/apps/web/out ./web    # ← the PWA goes here

# Push
huggingface-cli upload --repo-type space --private barnymurt/trg-agent . .

# Same for the other two (public)
```

### 5. Add the Anthropic key to `trg-agent`

1. Go to <https://huggingface.co/spaces/barnymurt/trg-agent/settings>
2. Variables and secrets → Add a **secret**:
   - `ANTHROPIC_API_KEY` = `sk-ant-...`
3. The Space restarts automatically.

### 6. Wait for builds

HF Spaces take 5–10 min for the first build (downloads ~50 MB of base image + a few MB of models on demand). Watch the logs:

- <https://huggingface.co/spaces/barnymurt/trg-agent/logs>
- <https://huggingface.co/spaces/barnymurt/trg-voice/logs>
- <https://huggingface.co/spaces/barnymurt/trg-embeddings/logs>

### 7. Smoke test

```bash
curl https://barnymurt-trg-agent.hf.space/health
curl https://barnymurt-trg-voice.hf.space/health
curl https://barnymurt-trg-embeddings.hf.space/health
```

Open the URL in your browser:

```
https://barnymurt-trg-agent.hf.space
```

You should see the chat interface. Tap the mic to test voice (Whisper cold-starts on first use, may take 30s).

### 8. Install on the professor's phone

On her iPhone:
1. Open the URL in Safari
2. Tap **Share → Add to Home Screen**
3. She now has an app icon

## Daily operations

### Update the agents / UI

```bash
git commit -am "feat: ..."
git push
# GitHub Actions auto-deploy to all three Spaces
```

### Rotate the Anthropic API key

1. <https://console.anthropic.com/settings/keys> — revoke old, create new
2. <https://huggingface.co/spaces/barnymurt/trg-agent/settings> → update the secret
3. Space restarts with the new key

### Inspect costs

- Anthropic: <https://console.anthropic.com/settings/billing>
- HF: <https://huggingface.co/settings/billing>
- Audit log: in the PWA, tap the clock icon (top-right)

### Backup

HF Spaces persist `/data` automatically. For off-platform backups, run a scheduled GitHub Action (already added as a stub at `.github/workflows/backup.yml` if you want to flesh it out).

## When something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Space build fails | Dockerfile error | Check logs; the Dockerfile is in `deploy/hf_spaces/trg-agent/` |
| `/health` returns 200 but `/` returns 404 | PWA `out/` wasn't uploaded | Rebuild the PWA (`pnpm --filter @trg/web build`) and re-upload |
| Chat says "anthropic.AuthenticationError" | Key missing or wrong | Add it to Space Settings → Variables and secrets |
| Voice button does nothing | `trg-voice` not deployed, or first Whisper cold-start | Wait 30s on first voice input |
| Embeddings 503 | `trg-embeddings` not yet deployed | Trigger workflow with `trg-embeddings` |

## Without any tokens (free public demo)

You can deploy everything as **PUBLIC** Spaces (no Pro needed) for a working demo with empty data:

```bash
huggingface-cli repo create trg-agent --type space --space-sdk docker --public
# … upload everything …
# No ANTHROPIC_API_KEY needed if TRG_DEMO_MODE=true
```

The chat will return canned responses (useful for showing the professor what the UI looks like). To use real Claude, add `ANTHROPIC_API_KEY` as a Space variable.

## Local dev counterpart

For local development: see [`infra/SETUP.md`](infra/SETUP.md).
