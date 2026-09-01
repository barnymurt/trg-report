# TRG — Setup Guide for the Professor

This guide is written for someone who isn't a developer. Every step says exactly what to click, what to type, and what to expect. If anything goes wrong, the **decision tree at the bottom** tells you where to look.

Total time: about 30–45 minutes the first time. Most of it is waiting for downloads.

---

## What you're installing

A small team of AI agents that runs on your laptop. It can listen to you (voice), answer questions about your house remodel and your medical records, and prepare things for you to approve before anything is sent anywhere.

All the AI work happens on your laptop. The only thing that goes to the internet is the actual answer from Claude (the LLM). Every Claude call is logged and you can read the log any time from the PWA.

---

## Step 1 — Install Docker Desktop

Docker is the software that runs all the agent services in the background. It's a free download.

- **Mac:** <https://www.docker.com/products/docker-desktop/> → click *Download for Mac* (Apple Silicon or Intel, whichever your Mac is)
- **Windows:** <https://www.docker.com/products/docker-desktop/> → click *Download for Windows*
- **Linux:** follow the Docker Engine install instructions for your distro

After installing:

- **Mac:** open *Docker Desktop* from your Applications folder. You'll see a whale icon in the menu bar at the top right. Wait until it stops animating — that means Docker is ready.
- **Windows:** open *Docker Desktop* from the Start menu. You'll see a whale icon in the system tray (bottom-right of your screen). Wait until it stops animating.

If you've never used Docker before, the first launch may ask you to sign in or create a Docker ID. You can skip sign-in (close the prompt) — we don't need an account.

---

## Step 2 — Open a terminal

You need a window where you can type commands. The terminal looks a bit intimidating at first but you only need to type or copy-paste the commands shown here.

- **Mac:** press `Cmd + Space`, type `Terminal`, press Enter
- **Windows:** press the Windows key, type `PowerShell`, right-click *Windows PowerShell* and choose *Run as Administrator*

---

## Step 3 — Install Node.js

If you've never installed Node before, get it from <https://nodejs.org/> — click the big **LTS** button. After installing, close and reopen your terminal.

Check it worked:

```bash
node --version
```

You should see something like `v20.x.x` or `v22.x.x`.

---

## Step 4 — Get the code

In your terminal:

```bash
cd ~
git clone https://github.com/barnymurt/trg-report.git trg
cd trg
```

If `git` isn't installed:
- **Mac:** in the terminal, type `xcode-select --install` and accept the prompt
- **Windows:** install from <https://git-scm.com/download/win> (use defaults)

---

## Step 5 — Enable pnpm

```bash
corepack enable
```

You should see no output. That's fine.

---

## Step 6 — Configure your API key

The agent needs an Anthropic API key. You create one at <https://console.anthropic.com/settings/keys>.

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open the new `.env` file in any text editor (TextEdit, Notepad, VS Code). Find the line that starts with `ANTHROPIC_API_KEY=` and replace the placeholder with your real key:

```
ANTHROPIC_API_KEY=sk-ant-...your-actual-key-here...
```

Save the file.

---

## Step 7 — Run the diagnostic

```bash
bash infra/scripts/preflight.sh
```

You'll see a colour-coded report:

- **Green ✓** — good to go
- **Yellow ⚠** — warning, probably OK
- **Red ✗** — needs fixing before continuing

Common issues the preflight catches:

| Red message | Fix |
|---|---|
| `Docker daemon not reachable` | Open Docker Desktop and wait for the whale icon to stop animating |
| `Docker Desktop not installed` | Re-do Step 1 |
| `WSL not detected` (Windows) | In an Administrator PowerShell: `wsl --install`, then restart |
| `Port NNNN already in use` | Stop whatever else is using that port, or edit `infra/docker-compose.yml` and change the published port |
| `RAM: N GB (< 16 GB required)` | The full stack won't run. Run `bash infra/scripts/install-native.sh --dry-run` to see a lighter alternative |
| `ANTHROPIC_API_KEY not set` | Re-do Step 6 |
| `huggingface.co unreachable` | Check your internet connection — the model downloads need this |

Re-run the preflight until every red is gone.

---

## Step 8 — Install the JavaScript dependencies

```bash
pnpm install
```

This downloads the PWA's code packages. Takes 1–2 minutes.

---

## Step 9 — Start the agents

```bash
pnpm infra:up
```

You'll see Docker pull a bunch of images and start ~10 containers. **The first time takes 5–10 minutes** — it's downloading the AI models (about 10 GB total). Subsequent starts take ~30 seconds.

When it's done you'll see all the containers with status `(healthy)`.

---

## Step 10 — Start the agent backend

In a new terminal (or the same one, but the previous one will be busy with Docker logs):

```bash
cd ~/trg
cd apps/agent
pip install -e .
uvicorn trg.main:app --host 0.0.0.0 --port 8001
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8001
INFO:     Application startup complete.
```

Leave this running. It uses a small amount of CPU when idle.

---

## Step 11 — Start the web app

In yet another terminal:

```bash
cd ~/trg
pnpm --filter @trg/web dev
```

You'll see:

```
- ready started server on 0.0.0.0:3000, url: http://localhost:3000
```

Open <http://localhost:3000> in your browser.

---

## Step 12 — Keep the laptop awake

If you want the agents to be reachable from your phone when you're out of the house, the laptop must stay awake. Run this once:

**Mac:**
```bash
bash infra/scripts/setup-power.sh
```

**Windows (PowerShell as Administrator):**
```powershell
bash infra/scripts/setup-power.sh
```

This configures power + Docker autostart so the system comes back to life after a reboot without you doing anything.

---

## Step 13 (optional) — Use it from your phone

This is only needed if you want voice access when you're not at home.

1. Sign up for Cloudflare at <https://dash.cloudflare.com/sign-up> (free).
2. Install `cloudflared` on your laptop: <https://pkg.cloudflare.dev/>
3. Create a tunnel:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create trg
   ```
4. Edit `infra/cloudflare/config.yml` with the tunnel ID and replace `trg.example.com` with a domain you own (or use the `*.trycloudflare.com` quick tunnel).
5. Run `cloudflared tunnel --config infra/cloudflare/config.yml run trg` in the background.

Now you can open `https://trg.example.com` on your phone, anywhere.

---

## Decision tree — something's wrong

```
Nothing happens when I open localhost:3000
├── "This site can't be reached"
│   └── Did you start the web app? (Step 11)
│   └── Is the agent backend running? (Step 10)
├── Page loads but says "Couldn't reach agent backend"
│   └── The agent backend isn't running. Start it (Step 10).
│   └── If it crashed, scroll up in the terminal and read the error.
│
The chat replies with "Claude API error"
└── Your ANTHROPIC_API_KEY is wrong or expired. Re-do Step 6.

The chat replies are slow / empty
└── Are all Docker containers healthy? Run `pnpm infra:ps`.
    Restart any that aren't: `docker compose -f infra/docker-compose.yml restart <name>`

Models won't download
└── Run `bash infra/scripts/preflight.sh` again.
    Check the Network section.
    If you're behind a corporate firewall or VPN, this may need IT help.

Nothing works and I just want to start over
└── From the repo root:
    pnpm infra:down
    docker compose -f infra/docker-compose.yml down --volumes
    rm -rf data/
    Then re-do from Step 9.
```

---

## Where things live on your computer

```
~/trg/
├── apps/
│   ├── web/          — the chat interface (Next.js)
│   └── agent/        — the AI brain (Python + FastAPI)
├── data/             — your documents and agent memory (DO NOT DELETE)
│   ├── documents/    — uploaded PDFs/images
│   ├── calendar/     — .ics files the agent creates for your approval
│   ├── drafts/       — email drafts for your approval
│   ├── share-queue/  — briefs to share with builders
│   ├── briefs/       — appointment briefs
│   └── audit.db      — log of every Claude call (right-to-delete lives here)
├── infra/
│   ├── docker-compose.yml
│   └── scripts/      — preflight, install-native, setup-power, backup
├── .env              — your API keys (NEVER commit this to git)
└── README.md
```

---

## When you're done for the day

The agents don't need to be running when you're not using them. To shut everything down:

```bash
pnpm infra:down           # stops Docker containers
```

The web app and agent backend stop when you close their terminals (or `Ctrl+C`).

To start everything again next time:

```bash
pnpm infra:up
# then in another terminal: cd apps/agent && uvicorn trg.main:app --host 0.0.0.0 --port 8001
# then in another terminal: pnpm --filter @trg/web dev
```

Or — if you've done Step 12 — Docker and the power settings handle themselves after a reboot. You only need to start the agent backend + web app manually.

---

## Backups

Run this nightly (or set it up via Task Scheduler / cron):

```bash
bash infra/scripts/backup.sh
```

It snapshots Qdrant, the audit log, and documents to `backups/`. The script is idempotent and safe.

To send backups to iCloud/OneDrive/Google Drive: configure your cloud sync client to include the `backups/` folder.

---

## Privacy controls

- **Audit log** — view from the PWA: tap the clock icon top-right.
- **Right-to-delete** — from the same view, tap "Wipe project" on any project. Removes all audit entries for that project.
- **Stop sharing with Claude** — set `ANTHROPIC_BETA=prompt-caching-2024-07-31` in `.env` (already on by default), and disable training-data usage in your Anthropic console.

---

## Help

If you get stuck:
1. Run `bash infra/scripts/preflight.sh` and read what it says.
2. Look at the bottom of the SETUP.md decision tree.
3. Capture the error and send it to whoever set this up for you.
