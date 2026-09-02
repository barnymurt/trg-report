# TRG — Deployment on Oracle Cloud Always Free

**$0/mo forever.** 4 vCPU + 24 GB ARM Ampere (or 1 GB x86 fallback) in your home region. Full stack — agent, voice, embeddings, PWA — on one VM, persistent URL via Cloudflare Tunnel.

> Verified against the Oracle Cloud console as of Sept 2026. UI screenshots referenced inline.

---

## Step 1 — Sign up

1. <https://www.oracle.com/cloud/free/>
2. Sign up with email + phone verification + credit card (Always Free is never charged; set a $1 budget alarm just in case)
3. **Choose your Home Region** carefully — pick the closest to where the professor is (UK → **London** or Amsterdam or Frankfurt). You can't change this later.
4. Skip the "guided tour" popups

## Step 2 — Create the network (VCN)

Skip if you want — the instance-create wizard can do this for you. Otherwise:

1. **Networking → Virtual Cloud Networks → Start VCN Wizard → Create VCN with Internet Connectivity**
2. Defaults are fine. The wizard creates:
   - VCN (e.g. `vcn-20260902-1715`)
   - A public subnet
   - An Internet Gateway + NAT Gateway

## Step 3 — Create the VM

1. **Compute → Instances → Create Instance**
2. **Name:** `trg-agent`

### Shape

3. Click **Edit** next to "Shape and resources"
4. **Instance shape → Ampere → VM.Standard.A1.Flex**
5. Set:
   - **Number of OCPUs: 4** (or whatever is available — start with 1 if 4 says "out of capacity")
   - **Amount of memory (GB): 24** (scales with OCPUs: 1 OCPU = 6 GB, 2 = 12 GB, 3 = 18 GB, 4 = 24 GB)
   - If the region says "Out of capacity for shape VM.Standard.A1.Flex" → try a different **Availability Domain** in the same region, or a smaller config (e.g. 1 OCPU / 6 GB). **Don't** drop to `VM.Standard.E2.1.Micro` unless you accept a degraded deployment (see "Small VM fallback" below)

### Image and networking

6. **Image:** click Edit → **Canonical Ubuntu** → **22.04** (or 24.04). Avoid Oracle Linux for now — our `setup.sh` prefers Ubuntu but works on both
7. **Networking:**
   - VCN: the one you created in Step 2 (or create a new one — defaults are fine)
   - Subnet: the **public** subnet
   - **☑️ Automatically assign a public IPv4 address** — this is critical; without it you can't SSH from your laptop
8. **Boot volume:** click Specify custom size → **200 GB** (free tier includes 200 GB)

### SSH keys

9. **SSH keys:** either
   - **Generate a key pair** → Oracle generates the keys; **download both .pub and .key immediately** (the private key is shown once), or
   - **Upload public key files** → paste your existing `.pub` (you already have `C:\Users\bmurt\Downloads\ssh-key-2026-09-02.key` — the matching `.pub` should be in the same folder)
10. Click **Create**

Boot takes 30-60 seconds. When the instance shows **Running**, click on it and copy the **Public IP address**.

## Step 4 — Open the network ports

1. **Networking → Virtual Cloud Networks → your VCN → Subnets → public subnet → Default Security List**
2. **Add Ingress Rules:**
   - Source CIDR: `0.0.0.0/0`
   - Protocol: TCP
   - Destination port: `80`
3. Repeat for `443` and `7860` (Cloudflare Tunnel will use these)

## Step 5 — SSH in and bootstrap

From your laptop, PowerShell or Terminal:

```bash
ssh -i "C:\Users\bmurt\Downloads\ssh-key-2026-09-02.key" ubuntu@<PUBLIC_IP>
```

(On first connect: type `yes` to trust the host key. If you get a "permissions too open" error: `icacls "C:\Users\bmurt\Downloads\ssh-key-2026-09-02.key" /inheritance:r /grant:r "$($env:USERNAME):(R)"` on Windows.)

On the VM:

```bash
git clone https://github.com/barnymurt/trg-report.git trg
cd trg
cp .env.example .env
nano .env      # set ANTHROPIC_API_KEY=sk-ant-... (Ctrl-O to save, Ctrl-X to exit)
bash infra/oracle/setup.sh
```

The script will:

1. Install Docker (works on Ubuntu or Oracle Linux, ARM or x86)
2. Detect your RAM and pick a deployment profile (`full` / `core` / `minimal`)
3. Pull all images (~5-10 min on first run)
4. Start the stack in the background
5. Install a **systemd watchdog** so the stack restarts after VM reboots
6. Print a Cloudflare quick-tunnel URL

The whole thing takes 10-15 minutes, mostly image pulls.

## Step 6 — Get the URL

When `setup.sh` prints:

```
PUBLIC URL (Cloudflare quick tunnel):
https://trg-random-words-here.trycloudflare.com
```

That's the URL to give the professor. Open it on her phone, "Add to Home Screen", done.

The URL changes on every VM restart. For a stable URL:

### Stable URL (named Cloudflare Tunnel)

1. Sign up at <https://dash.cloudflare.com/>
2. **Zero Trust → Networks → Tunnels → Create a tunnel** (name: `trg-agent`, type: Cloudflared)
3. Copy the install command; on the VM:
   ```bash
   curl -L --output cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
   sudo mv cloudflared /usr/local/bin/cloudflared && sudo chmod +x /usr/local/bin/cloudflared
   sudo cloudflared service install <YOUR_TOKEN>
   ```
4. Add a public hostname: `trg.yourdomain.com` → `http://localhost:7860`

(Requires you to own a domain and have its nameservers pointed at Cloudflare, ~€10/yr on Cloudflare Registrar.)

---

## Architecture

```
┌─── Oracle Cloud Always Free VM (1-4 OCPU, 6-24 GB, Ubuntu) ──┐
│                                                                   │
│  Docker Compose stack (adapted to RAM):                          │
│    - agent       FastAPI + serves PWA at /                        │
│    - qdrant      vector DB                                       │
│    - tei-embeddings  bge-small (full / core)                    │
│    - tei-multilingual  bge-m3   (full only)                      │
│    - tei-reranker     bge-reranker (full only)                   │
│    - whisper     faster-whisper (full / core)                   │
│    - kokoro      Kokoro TTS (full / core)                        │
│    - smollm2     llama.cpp (full only, 4 GB RAM+)               │
│    - docling     granite-docling-258M (full only, 8 GB RAM+)    │
│    - caddy       reverse proxy                                    │
│    - cloudflared tunnel                                           │
│                                                                   │
│  systemd watchdog restarts unhealthy services                    │
│  nightly backup → /opt/trg-backups                               │
└───────────────────────────────────────────────────────────────────┘
                │
                ▼
       Cloudflare edge (HTTPS, free)
                │
                ▼
   Professor's phone → https://trg.yourdomain.com
```

---

## Deployment profiles (auto-selected by RAM)

| Profile | RAM | What runs | What you give up |
|---|---|---|---|
| **full** | ≥12 GB | agent + Qdrant + TEI-EN + TEI-multilingual + reranker + whisper + kokoro + smollm2 + docling | nothing |
| **core** | 6-11 GB | agent + Qdrant + TEI-EN + whisper + kokoro (smaller resource limits) | reranker + docling — falls back to HF Inference API |
| **minimal** | 2-5 GB | agent + Qdrant + TEI-EN only | voice, reranker, docling — heavy use of HF Inference API |
| **micro** | <2 GB | not recommended for this VM shape | — |

On the `minimal` profile, set `HF_TOKEN` in `.env` to enable HF Inference API for the disabled services. The agent automatically falls back.

---

## Small VM fallback (if A1.Flex isn't available in your region)

If `VM.Standard.A1.Flex` keeps saying "out of capacity" (common in London and Frankfurt during peak hours), you have two options:

### Option A — keep retrying
Capacity frees up regularly. Run a script that retries every 5 min until it succeeds: <https://github.com/hitrov/oci-arm-host-capacity>

### Option B — accept the E2.1.Micro shape (1 GB ARM-less x86)
Free forever but tiny. The setup script will detect 1 GB RAM and run in `minimal` profile + aggressively use HF Inference API for embeddings/Whisper/Kokoro. The chat still works; voice input/output will feel slower (round-trip to HF).

Either way, the URL is the same.

---

## After setup

### Update the agents / UI

```bash
ssh ubuntu@<PUBLIC_IP>
cd ~/trg
git pull
sudo systemctl restart trg-watchdog
```

### Rotate the Anthropic API key

```bash
ssh ubuntu@<PUBLIC_IP>
cd ~/trg
nano .env   # set ANTHROPIC_API_KEY=sk-ant-new-key-...
sudo systemctl restart trg-watchdog
```

### Manage the stack

```bash
sudo systemctl {status,start,stop,restart} trg-watchdog
cd ~/trg && docker compose -f infra/docker-compose.yml -f infra/docker-compose.<profile>.yml logs -f
cd ~/trg && docker compose -f infra/docker-compose.yml -f infra/docker-compose.<profile>.yml ps
```

### Backups

```bash
ssh ubuntu@<PUBLIC_IP>
sudo tar -czf /opt/trg-backups/manual-$(date +%Y%m%d).tar.gz ~/trg/data
```

To copy off the VM (to your laptop):
```powershell
scp -i "C:\Users\bmurt\Downloads\ssh-key-2026-09-02.key" ubuntu@<PUBLIC_IP>:/opt/trg-backups/* ./backups/
```

Or attach an OCI Object Storage bucket (free 10 GB) and push backups there.

### Budget alarm (safety net)

1. **Billing & Cost Management → Budgets → Create Budget**
2. Budget amount: **$1/mo**
3. Alert thresholds: 50%, 80%, 100%

You'll get an email if anything starts billing.

### Housekeeping

```bash
# Confirm total storage stays under 200 GB
oci bv volume list --compartment-id <your-compartment-ocid> --query 'data[]."size-in-gbs"' --output table

# Delete any orphaned boot volumes from terminated instances
Storage → Boot Volumes → select → Terminate
```

---

## When something goes wrong

| Symptom | Fix |
|---|---|
| `ssh` asks for password instead of using the key | The `.pub` you uploaded doesn't match the `.key` you're using. Re-create the VM with matching pair. |
| `connection refused` on port 22 | Public IP not assigned (you forgot the checkbox). Add one: Compute → Instances → your VM → Edit → Attached VNICs → Add IPv4. |
| `Out of host capacity` for A1.Flex | Retry later, or accept E2.1.Micro with the `minimal` profile. |
| `setup.sh` fails on `apt-get` | You're on Oracle Linux without `apt`. The script auto-detects; if it fails, share the error. |
| Stack OOMs during image pull | The VM is too small for the profile. Re-run `setup.sh` after lowering profile in `.env`. |
| `Could not connect to the Docker daemon` | You haven't been added to the docker group yet, or need to log out/in. Run `newgrp docker` and re-run setup.sh. |
| Cloudflare quick tunnel URL changes after reboot | Expected. Switch to a named tunnel (see Step 6 above). |

---

## When you outgrow the free tier

- **More RAM on OCI:** same shape, just request it (Paid account only, ~$0.02/hr for 4 OCPU/24 GB)
- **Hetzner CX32:** 4 vCPU, 8 GB, 80 GB SSD at €7/mo, EU — simpler UI, no capacity games
- **Render.com:** ~$7/mo starter, simpler than OCI but US-based
