# Plan: TRG Agent Team on Oracle Cloud A1.Flex ARM

> **What:** Stand up the full TRG stack on a real free-tier ARM VM (24 GB RAM, 4 vCPU, forever free) and hand back a permanent URL.
>
> **Who:** Anyone with an Oracle Cloud account and ~30 minutes.
>
> **Why A1.Flex, not E2.1.Micro:** the E2.1.Micro shape exposes only ~498 MB usable RAM, which is not enough to build Python Docker images (pip install needs ~1 GB, so it OOMs). The A1.Flex ARM shape gives 24 GB RAM and handles the full stack easily.
>
> **Time:** ~30 min first time (most is waiting for image downloads and shape capacity).

---

## 0. Prerequisites (5 min)

- [ ] Oracle Cloud account: <https://cloud.oracle.com/> (free, sign up)
- [ ] Credit card on file (verification only — the Always Free tier never charges)
- [ ] Anthropic API key: <https://console.anthropic.com/settings/keys>
- [ ] SSH key pair on your laptop (run `ssh-keygen -t ed25519` if you don't have one)
- [ ] A name + email registered on OCI (you'll use it for the home region pick)

**Pick your Home Region carefully** — it's permanent. Pick the one closest to the user (UK → **London** first, then **Amsterdam** or **Stockfurt** as backups).

---

## 1. Sign in and create the VM (10 min)

Open <https://cloud.oracle.com/compute/instances>.

### 1a. Click **Create Instance**

### 1b. Fill in basics

- **Name:** `trg-agent`
- **Compartment:** root (default)

### 1c. Pick the image and shape

Click **Edit** next to "Image and shape".

#### Image
- **Select:** Canonical Ubuntu (NOT Oracle Linux, NOT Ubuntu from a different vendor)
- **Version:** 22.04 (or 24.04 — both work)
- For shape: click **Edit** → **Ampere** → **VM.Standard.A1.Flex**
  - Start with **1 OCPU / 6 GB RAM** (more available in capacity-constrained regions)
  - If 4 OCPU / 24 GB shows "Out of capacity", fall back to 1/6, 2/12, or 3/18 — they're all within the same Always Free quota, just need different capacity slots
  - Whatever you claim is yours; you can resize later

#### Capacity fallback strategy

London and Frankfurt are often fully booked. Try this in order:
1. Try London (or your home region) at 4 OCPU / 24 GB — wait 5-10 min between retries
2. If always "out of capacity", drop to 1 OCPU / 6 GB (still works)
3. Try Amsterdam, then Stockholm, then Marseille as fallback home regions (changing requires account recreation)
4. As a last resort: use the "Out of Capacity" issue script at <https://github.com/hitrov/oci-arm-host-capacity> which retries every 5 min

### 1d. Networking

- Create a new VCN (defaults fine)
- **Subnet:** the auto-created public subnet
- **☑️ Assign a public IPv4 address** ← **CRITICAL — do not skip this**

If you forget the public IPv4, the VM will be unreachable. The UI label is slightly hidden in some console versions — look under the "Networking" section of the create wizard. If unsure, expand all sections.

### 1e. Boot volume

Click **Specify custom size** → set to **200 GB** (the free-tier 200 GB quota, gives plenty of room for Docker images + logs + backups).

### 1f. SSH keys

**Generate a key pair and save BOTH files** (.pub and .key):
- Paste your existing `.pub` if you have one
- Or click **Generate a key pair** → **download both files immediately** (the private key is only shown once)

Save them somewhere safe — `C:\Users\<you>\.ssh\oci-trg-agent.key` is a good location on Windows.

### 1g. Click **Create**

Boot takes 30-60 seconds. When the instance state turns **Running** and you can see a **Public IP** in the instance details, you're ready.

**Copy the public IP** — you'll need it for SSH.

---

## 2. Open the network ports (2 min)

The default VCN security list only allows SSH (port 22). We need to open the rest for Cloudflare Tunnel and the agent itself.

1. **Networking → Virtual Cloud Networks** → click your VCN
2. **Subnets** → click the public subnet
3. **Default Security List** → **Add Ingress Rules**
4. Add four rules:

| Source CIDR | Protocol | Destination Port | Purpose |
|---|---|---|---|
| 0.0.0.0/0 | TCP | 22 | SSH |
| 0.0.0.0/0 | TCP | 80 | HTTP fallback |
| 0.0.0.0/0 | TCP | 443 | HTTPS fallback |
| 0.0.0.0/0 | TCP | 7860 | Agent API |

5. **Save**

---

## 3. SSH in (1 min)

From your laptop PowerShell:

```powershell
ssh -i "C:\Users\YOU\.ssh\oci-trg-agent.key" ubuntu@<PUBLIC_IP_FROM_STEP_1G>
```

First connect: type `yes` to trust the host key. If you get "Permissions are too open" on Windows:
```powershell
icacls "C:\Users\YOU\.ssh\oci-trg-agent.key" /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

You should land at a prompt like `ubuntu@trg-agent:~$`.

---

## 4. Bootstrap the stack (10-15 min, mostly waiting)

**Single command** — installs everything and prints the live URL:

```bash
git clone https://github.com/barnymurt/trg-report.git trg
cd trg
cp .env.example .env
nano .env   # set ANTHROPIC_API_KEY=sk-ant-...your-key-here, Ctrl-O to save, Ctrl-X to exit
bash infra/oracle/setup.sh
```

The script will:
1. Install Docker Engine + Compose plugin
2. Pull all images (~10 min on first run, mostly bge-small embedder at 130 MB and Qdrant at 100 MB)
3. Start the full stack (Qdrant, TEI embeddings, reranker, Whisper, Kokoro, SmolLM2 router, agent backend, Caddy reverse proxy, Cloudflared tunnel)
4. Install a systemd watchdog so the stack restarts automatically on VM reboot
5. Print a Cloudflare quick-tunnel URL

**When you see `PUBLIC URL:` at the end of the script output, that's the URL for the professor.** It looks like:

```
PUBLIC URL (Cloudflare quick tunnel):
https://trg-random-words-here.trycloudflare.com
```

The URL is random and changes on every VM restart. To get a stable URL, follow step 5.

---

## 5. (Optional) Stable URL via named Cloudflare Tunnel

The random URL works fine for testing. For a stable URL that survives reboots:

1. Sign up at <https://dash.cloudflare.com/> (free)
2. **Zero Trust → Networks → Tunnels → Create a tunnel**
3. Name: `trg-agent`. Save the **Tunnel Token**.
4. On the VM:
   ```bash
   curl -L --output /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
   sudo chmod +x /usr/local/bin/cloudflared
   sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
   ```
5. Add a public hostname: `trg.yourdomain.com` → `http://localhost:7860`

Requires you to own a domain (~$10/yr on Cloudflare Registrar).

---

## 6. Verification checklist

After the bootstrap finishes:

- [ ] Visit `http://<PUBLIC_IP>:7860/health` → returns `{"status":"ok"...}`
- [ ] Visit the Cloudflare URL on your phone → PWA loads
- [ ] Tap the mic → speak → see response (Whisper first use takes ~30s for cold-start)
- [ ] Open the audit log (clock icon top-right of PWA)
- [ ] Send a test email draft → approve in the Pending Actions tray → check `data/drafts/` on the VM

---

## 7. Day-to-day operations

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
nano .env      # replace the ANTHROPIC_API_KEY line
sudo systemctl restart trg-watchdog
```

### Inspect the stack

```bash
ssh ubuntu@<PUBLIC_IP>
sudo systemctl status trg-watchdog
cd ~/trg && pnpm infra:ps          # container status
cd ~/trg && pnpm infra:logs        # tail logs
```

### Backups

The setup script installs a systemd timer that runs `infra/scripts/backup.sh` nightly. Backups land in `/opt/trg-backups/` on the VM. To copy them off:

```powershell
scp -i "C:\Users\YOU\.ssh\oci-trg-agent.key" -r ubuntu@<PUBLIC_IP>:/opt/trg-backups/ C:\Dev\TRG\backups\
```

---

## 8. When something goes wrong

| Symptom | Fix |
|---|---|
| `bash: setup.sh: No such file or directory` | You forgot `cd trg` first |
| `docker: command not found` | Script's Docker install step failed. Run `sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin` (Ubuntu has more RAM so this should work directly) |
| `Permission denied (publickey)` | The key you uploaded doesn't match the `.key` file. Re-upload or check the path |
| `Connection refused` on port 22 | Public IP not assigned. Edit the instance → Attached VNICs → add IPv4 |
| `Connection timed out` | Security list doesn't allow port 22. Re-check step 2 |
| `Out of capacity for shape VM.Standard.A1.Flex` | Try a smaller config (1 OCPU / 6 GB) or a different region. See fallback strategy in step 1c |
| `agent service unhealthy` | `sudo systemctl restart trg-watchdog`. If that doesn't fix it, `cd ~/trg && docker compose -f infra/docker-compose.yml logs agent` |
| Cloudflare URL says "no healthy backends" | The agent isn't listening on 7860 yet. Wait 30s for cold start. Check `docker compose ps` |

---

## 9. Cost summary

| Item | Cost |
|---|---|
| VM.Standard.A1.Flex (4 OCPU, 24 GB) | $0 (Always Free) |
| Block storage (200 GB) | $0 (Always Free) |
| Outbound transfer (10 TB/mo) | $0 (Always Free) |
| Anthropic API (Haiku-heavy use) | ~$1–5/mo at her volume |
| Cloudflare Tunnel (named) | $0 |
| Domain (optional, for stable URL) | ~$10/yr |
| **Total** | **~$1–5/mo** |

---

## 10. When you outgrow the free tier

- **More RAM on OCI:** same shape, just request it. Paid account only, ~$0.02/hr for 4 OCPU/24 GB.
- **Hetzner CX32:** 4 vCPU, 8 GB, 80 GB SSD at €7/mo, EU — simpler UI.
- **Render.com starter:** ~$7/mo, US, simpler than OCI.

The setup script works on any of these — only the bootstrap path changes.
