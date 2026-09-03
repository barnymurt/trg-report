#!/usr/bin/env bash
# find-or-attach-public-ip.sh
#
# Paste this into OCI Cloud Shell (the >_ icon at the top right of the
# console). It will:
#   1. List all instances in your tenancy
#   2. Let you pick one
#   3. Get its VNIC + private IP OCID via the instance get endpoint
#      (this works even when vnic-list returns empty due to per-compartment
#      permission boundaries)
#   4. Create a free ephemeral public IPv4
#   5. Attach it to the VNIC's private IP
#   6. Print the SSH command + bootstrap instructions
#
# No credentials needed — Cloud Shell is already authenticated to your
# Oracle tenancy via InstancePrincipal.

set -euo pipefail

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[0;32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[1;33m⚠\033[0m %s\n" "$1"; }
die()  { printf "  \033[0;31m✗\033[0m %s\n" "$1"; exit 1; }

# ─── Preflight ─────────────────────────────────────────────────────────
command -v oci >/dev/null 2>&1 || die "oci CLI not found in Cloud Shell — are you sure you're in Cloud Shell? (top right >_ icon)"
command -v jq >/dev/null 2>&1 || die "jq not found (should be preinstalled in Cloud Shell)"

# Cloud Shell sets OCI_COMPARTMENT and OCI_TENANCY. Use either.
COMPARTMENT_ID="${OCI_COMPARTMENT:-$OCI_TENANCY}"
[ -n "$COMPARTMENT_ID" ] || die "Could not determine tenancy/compartment. Set OCI_COMPARTMENT=<ocid> and re-run."
ok "compartment: $COMPARTMENT_ID"

# ─── Step 1: list all instances ────────────────────────────────────────
step "Instances in your tenancy:"
oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query 'data[].{"display-name":"display-name",id:id,shape:shape,state:"lifecycle-state","public-ip":"public-ip"}' \
  --output table

# ─── Step 2: ask which one ─────────────────────────────────────────────
echo ""
DEFAULT_NAME=$(oci compute instance list --compartment-id "$COMPARTMENT_ID" --query 'data[0]."display-name"' --raw-output 2>/dev/null || true)

if [ -t 0 ]; then
  read -r -p "Which instance do you want a public IP on? (press Enter for: ${DEFAULT_NAME:-first one}): " INPUT_NAME
  INSTANCE_NAME="${INPUT_NAME:-$DEFAULT_NAME}"
else
  INSTANCE_NAME="$DEFAULT_NAME"
fi

[ -n "$INSTANCE_NAME" ] || die "No instance name provided"

# ─── Step 3: get instance details (this includes VNIC info) ──────────
step "Fetching instance details (including VNIC)…"
INSTANCE_JSON=$(oci compute instance get --instance-id "$(oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query "data[?\"display-name\"=='$INSTANCE_NAME'].id | [0]" \
  --raw-output)" 2>/dev/null)
[ -n "$INSTANCE_JSON" ] || die "Could not fetch instance. Check that the name is correct."

# Use jq to extract VNIC + private IP info
VNIC_OCID=$(echo "$INSTANCE_JSON" | jq -r '.data.vnics[0].id // empty')
PRIVATE_IP=$(echo "$INSTANCE_JSON" | jq -r '.data.vnics[0]."private-ip" // empty')
SUBNET_OCID=$(echo "$INSTANCE_JSON" | jq -r '.data.vnics[0]."subnet-id" // empty')

[ -n "$VNIC_OCID" ] || die "No VNIC found on instance $INSTANCE_NAME"
ok "vnic:   $VNIC_OCID"
ok "privip: $PRIVATE_IP (subnet $SUBNET_OCID)"

# Check if a public IP is already assigned
EXISTING_PUBLIC_IP=$(echo "$INSTANCE_JSON" | jq -r '.data."public-ip" // empty')

if [ -n "$EXISTING_PUBLIC_IP" ] && [ "$EXISTING_PUBLIC_IP" != "null" ]; then
  ok "instance already has a public IP: $EXISTING_PUBLIC_IP"
  PUBLIC_IP="$EXISTING_PUBLIC_IP"
else
  # Get the private IP OCID (needed for the public-ip update)
  step "Fetching VNIC private IP OCID…"
  VNIC_JSON=$(oci network vnic get --vnic-id "$VNIC_OCID" 2>/dev/null)
  PRIVATE_IP_OCID=$(echo "$VNIC_JSON" | jq -r '.data."primary-private-ip".id // .data.id // empty')

  if [ -z "$PRIVATE_IP_OCID" ] || [ "$PRIVATE_IP_OCID" = "null" ]; then
    die "Could not determine private IP OCID. Try: oci network vnic get --vnic-id $VNIC_OCID"
  fi
  ok "privip OCID: $PRIVATE_IP_OCID"

  # ─── Step 4: create ephemeral public IP ──────────────────────────────
  step "Creating ephemeral public IPv4 address…"
  PUB_IP_JSON=$(oci network public-ip create \
    --compartment-id "$COMPARTMENT_ID" \
    --lifetime EPHEMERAL \
    --display-name "trg-${INSTANCE_NAME}-public" 2>&1)
  PUB_IP_EXIT=$?
  PUBLIC_IP=$(echo "$PUB_IP_JSON" | jq -r '.data."ip-address" // empty' 2>/dev/null || true)
  PUBLIC_IP_OCID=$(echo "$PUB_IP_JSON" | jq -r '.data.id // empty' 2>/dev/null || true)

  if [ "$PUB_IP_EXIT" -ne 0 ]; then
    die "public-ip create failed: $PUB_IP_JSON"
  fi
  if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" = "null" ]; then
    die "public-ip create returned no address: $PUB_IP_JSON"
  fi
  ok "created public IP: $PUBLIC_IP (ocid: $PUBLIC_IP_OCID)"

  # ─── Step 5: attach the public IP to the VNIC's private IP ──────────
  step "Attaching public IP to private IP…"
  ATTACH_JSON=$(oci network public-ip update \
    --public-ip-id "$PUBLIC_IP_OCID" \
    --private-ip-id "$PRIVATE_IP_OCID" 2>&1)
  ATTACH_EXIT=$?
  if [ "$ATTACH_EXIT" -ne 0 ]; then
    die "public-ip update failed: $ATTACH_JSON"
  fi
  ok "attached"
fi

# ─── Done ──────────────────────────────────────────────────────────────
step "Summary"
echo ""
echo -e "  Instance:  $INSTANCE_NAME"
echo -e "  Public IP: \033[1;32m$PUBLIC_IP\033[0m"
echo ""
echo -e "  \033[1mFrom your laptop (PowerShell), SSH in:\033[0m"
echo ""
echo -e "  \033[1;36mssh -i \"C:\\Users\\bmurt\\Downloads\\ssh-key-2026-09-02.key\" opc@$PUBLIC_IP\033[0m"
echo ""
echo -e "  \033[1mIf 'opc' doesn't work, try 'ubuntu' — depends on the image you picked.\033[0m"
echo ""
echo -e "  \033[1mThen on the VM:\033[0m"
echo ""
cat <<'EOF'
  git clone https://github.com/barnymurt/trg-report.git trg
  cd trg
  cp .env.example .env
  nano .env          # set ANTHROPIC_API_KEY=sk-ant-...
  bash infra/oracle/setup.sh
EOF
echo ""
echo -e "  \033[1mOne more thing — open these network ports in the OCI console:\033[0m"
echo -e "  Networking → VCN → Subnets → public subnet → Default Security List"
echo "  Add ingress rules: TCP 22, 80, 443, 7860 from 0.0.0.0/0"
echo ""
