<h1 align="center">
  <br>
  <br>
  TRG Agent Team on Oracle Cloud
  <br>
  <br>
</h1>

<p align="center">
  <strong>Free forever.</strong> 24 GB ARM VPS in the EU. Full stack (agent + voice + embeddings + PWA) on one machine.
</p>

<br>

## What you get

- **$0/mo** — Oracle Cloud "Always Free" tier
- **24 GB RAM, 4 vCPU** ARM (Ampere A1) — more than enough for the full stack
- **EU region** (Frankfurt, Amsterdam, or Stockholm)
- **Persistent URL** — Cloudflare Tunnel gives you `https://trg.example.com` (or `https://<random>.trycloudflare.com` for the quick tunnel)
- **24/7 uptime** — no laptop required

## Cost summary

| Item | Cost |
|---|---|
| Oracle Cloud VM.Standard.A1.Flex (4 OCPU, 24 GB) | $0 (Always Free) |
| Block storage 200 GB | $0 (Always Free) |
| Outbound data transfer (10 TB/mo) | $0 (Always Free) |
| Anthropic API | ~$1–5/mo (Haiku-heavy) |
| **Total** | **~$1–5/mo** |

---

## Step 1 — Sign up for Oracle Cloud (free)

1. Go to <https://cloud.oracle.com/>
2. Click **Start for Free**
3. Enter email, country, name
4. **Add a credit card** (verification only — they will never charge you on the Always Free tier; you can set a budget alarm to $1 to prove it)
5. Choose **Home Region**: pick the one closest to the user (UK → **London** or **Amsterdam** or **Frankfurt**)

The free ARM VM is region-specific. After signup, you can't change home region, so pick well.

## Step 2 — Create the free ARM VM

In the OCI console:

1. **Compute → Instances → Create Instance**
2. **Name:** `trg-agent`
3. **Placement:** your home region
4. **Image:** Ubuntu 22.04 (or 24.04) — **Canonical Ubuntu**, not Oracle Linux (we test on Ubuntu)
5. **Shape:** Click **Edit** → **Ampere** → **VM.Standard.A1.Flex**
   - **4 OCPUs, 24 GB RAM** (the full free quota — try to claim it; sometimes only partial is available)
   - If the region says "Out of capacity for shape VM.Standard.A1.Flex", try a different region or claim a smaller shape and retry later
6. **Networking:** create a new VCN (default settings are fine)
   - **Assign a public IPv4 address** ✓ (needed for SSH + initial setup)
7. **SSH keys:** paste your public key (generate one with `ssh-keygen -t ed25519` if you don't have one)
8. Click **Create**

Boot takes ~1 minute. Once the instance state is **Running**, note its **Public IP**.

## Step 3 — Configure OCI security list

Default OCI networking blocks all inbound except SSH. We need to open 80/443 for the Cloudflare Tunnel origin and 7860 as a fallback.

1. **Networking → Virtual Cloud Networks → your VCN → Subnets → public subnet → Security Lists → Default Security List**
2. **Add Ingress Rules:**
   - **Source CIDR:** `0.0.0.0/0`
   - **Protocol:** TCP
   - **Destination Port:** `80`, `443`, `7860`
   (Cloudflare Tunnel will use 7860 as the origin; opening 80/443 lets the tunnel also serve raw HTTP if needed.)

## Step 4 — SSH in and run the bootstrap

```bash
ssh ubuntu@<PUBLIC_IP>

# One-shot bootstrap — installs Docker, clones the repo, starts everything
curl -sSL https://raw.githubusercontent.com/barnymurt/trg-report/main/infra/oracle/setup.sh | bash
```

Or clone manually and run locally:

```bash
ssh ubuntu@<PUBLIC_IP>
git clone https://github.com/barnymurt/trg-report.git trg
cd trg
cp .env.example .env
nano .env   # fill in ANTHROPIC_API_KEY
bash infra/oracle/setup.sh
```

The script will:

1. Install Docker Engine + Compose plugin
2. Pull all images (Qdrant, TEI, Whisper, Kokoro, SmolLM2, the agent)
3. Start the full stack in the background
4. Print a URL when health checks pass

## Step 5 — Cloudflare Tunnel (free URL)

Two options:

### Option A — Quick tunnel (no account, URL changes on restart)

The setup script automatically starts a quick tunnel. Look for output like:

```
Your quick Tunnel has been created!
+-------------------------------------------+
| https://trg-random-words-here.trycloudflare.com |
+-------------------------------------------+
```

This URL is free, no signup, and works immediately. **Caveat:** the random subdomain changes every time the VM restarts. Good for getting started.

### Option B — Named tunnel (persistent URL)

1. Sign up at <https://dash.cloudflare.com/sign-up>
2. **Zero Trust → Networks → Tunnels → Create a tunnel**
3. Name: `trg-agent`
4. Install `cloudflared` on your laptop or the VM
5. **Run the tunnel command** from the Cloudflare dashboard — copy-paste into the VM
6. Add a public hostname: `trg.yourdomain.com` → `http://localhost:7860`

This gives a persistent URL. Update DNS in your domain registrar to point at Cloudflare's nameservers first.

---

## Architecture on Oracle Cloud

```
┌─── Oracle Cloud VM (VM.Standard.A1.Flex, 4 OCPU, 24 GB, Ubuntu) ──┐
│                                                                       │
│  Docker Compose stack:                                               │
│    - agent       (our FastAPI + serves PWA at /)                     │
│    - qdrant      (vector DB)                                          │
│    - tei-embeddings  (bge-small-en-v1.5)                              │
│    - whisper     (faster-whisper, distil-large-v3)                   │
│    - kokoro      (Kokoro-82M TTS)                                     │
│    - smollm2     (llama.cpp server)                                   │
│    - docling     (Granite-Docling-258M PDF ingest)                   │
│    - caddy       (HTTPS + reverse proxy)                             │
│    - cloudflared (tunnel to the internet)                            │
│                                                                       │
│  systemd watchdog restarts any unhealthy service                      │
│  nightly backup → /opt/trg-backups → user-mounted backup volume      │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
   Cloudflare edge (HTTPS, free)
        │
        ▼
   Professor's phone → https://trg.example.com
```

---

## After setup

### Update the agents

```bash
ssh ubuntu@<PUBLIC_IP>
cd trg
git pull
pnpm infra:restart
```

### Add the Anthropic API key (if you didn't at boot)

```bash
ssh ubuntu@<PUBLIC_IP>
cd trg
nano .env   # set ANTHROPIC_API_KEY=sk-ant-...
pnpm infra:restart
```

### Rotate the Anthropic API key

Same as above — edit `.env`, restart.

### Backups

Backups are written nightly to `/opt/trg-backups` inside the VM. To copy them off the VM:

```bash
rsync -avz ubuntu@<PUBLIC_IP>:/opt/trg-backups/ ./local-backups/
```

Or attach an OCI Object Storage bucket (free 10 GB) and configure the backup script to push there.

### Monitor

```bash
ssh ubuntu@<PUBLIC_IP>
cd trg
pnpm infra:ps         # service status
bash infra/scripts/healthcheck.sh
docker stats         # resource usage
```

---

## When something goes wrong

| Symptom | Fix |
|---|---|
| `pnpm infra:up` fails with "no space left" | Increase the boot volume (default 47 GB → 200 GB) in the VM details |
| `Cloudflare Tunnel` URL changes every restart | Switch to a named tunnel (Option B above) |
| ARM CPU is slow for Whisper/Kokoro | Use `--compute-type int8` (default) and `--cpu-threads 4` |
| Out of memory | The 24 GB ARM should be plenty; check `docker stats` for which container is leaking |
| Can't SSH after creating VM | Check OCI security list has port 22 open; verify your public IP matches what's in the VM's info |

---

## When you outgrow the free tier

If you need more than 24 GB or want a region outside the Always Free zones:
- **Oracle paid** — same console, same VM.Standard.A1.Flex at ~$0.02/hr
- **Hetzner CX32** — 4 vCPU, 8 GB, 80 GB SSD at €7/mo, EU, simple UI
- **Hetzner CAX21** — ARM 4 vCPU, 8 GB at €5/mo, EU (similar to OCI ARM but cheaper if OCI is full)
