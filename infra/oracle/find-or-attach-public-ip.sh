#!/usr/bin/env bash
# find-or-attach-public-ip.sh
#
# Paste into OCI Cloud Shell. Robust to older CLI versions and permission
# boundaries by trying multiple ways to find the VNIC and private IP.

set -euo pipefail

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[0;32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[1;33m⚠\033[0m %s\n" "$1"; }
die()  { printf "  \033[0;31m✗\033[0m %s\n" "$1"; exit 1; }

DEBUG="${DEBUG:-0}"

command -v oci >/dev/null 2>&1 || die "oci CLI not found in Cloud Shell"
command -v jq >/dev/null 2>&1 || die "jq not found (should be preinstalled)"

COMPARTMENT_ID="${OCI_COMPARTMENT:-$OCI_TENANCY}"
[ -n "$COMPARTMENT_ID" ] || die "No compartment/tenancy env var set. Run: export OCI_TENANCY=\$(oci iam tenancy get --query 'data.id' --raw-output)"
ok "compartment: $COMPARTMENT_ID"

# ─── Step 1: list all instances ────────────────────────────────────────
step "Instances in your tenancy:"
oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query 'data[].{"display-name":"display-name",id:id,shape:shape,state:"lifecycle-state","public-ip":"public-ip"}' \
  --output table

# ─── Step 2: pick the instance ─────────────────────────────────────────
echo ""
DEFAULT_NAME=$(oci compute instance list --compartment-id "$COMPARTMENT_ID" --query 'data[0]."display-name"' --raw-output 2>/dev/null || true)

if [ -t 0 ]; then
  read -r -p "Which instance? (Enter for: ${DEFAULT_NAME:-first one}): " INPUT_NAME
  INSTANCE_NAME="${INPUT_NAME:-$DEFAULT_NAME}"
else
  INSTANCE_NAME="$DEFAULT_NAME"
fi
[ -n "$INSTANCE_NAME" ] || die "No instance name provided"

INSTANCE_OCID=$(oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query "data[?\"display-name\"=='$INSTANCE_NAME'].id | [0]" \
  --raw-output 2>/dev/null)
[ -n "$INSTANCE_OCID" ] || die "No instance found with name '$INSTANCE_NAME'"
ok "instance: $INSTANCE_NAME ($INSTANCE_OCID)"

# ─── Step 3: get full instance details (raw JSON, for diagnostics) ───
step "Fetching full instance details…"
INSTANCE_JSON=$(oci compute instance get --instance-id "$INSTANCE_OCID" 2>&1) || die "instance get failed: $INSTANCE_JSON"

if [ "$DEBUG" = "1" ]; then
  echo "  raw instance JSON keys (top 30):"
  echo "$INSTANCE_JSON" | jq -r '.data | keys_unsorted[:30] | .[]' 2>/dev/null | sed 's/^/    /'
fi

# Try to detect public IP first
EXISTING_PUBLIC_IP=$(echo "$INSTANCE_JSON" | jq -r '.data."public-ip" // empty' 2>/dev/null || true)

# ─── Step 4: find the VNIC OCID (multiple strategies) ────────────────
step "Finding VNIC…"

VNIC_OCID=""

# Strategy 1: from instance.vnics
VNIC_OCID=$(echo "$INSTANCE_JSON" | jq -r '.data.vnics[0].id // empty' 2>/dev/null || true)
[ -n "$VNIC_OCID" ] && ok "VNIC (from .data.vnics): $VNIC_OCID"

# Strategy 2: from compute vnic-attachment list
if [ -z "$VNIC_OCID" ]; then
  ATTACH_JSON=$(oci compute vnic-attachment list \
    --compartment-id "$COMPARTMENT_ID" \
    --instance-id "$INSTANCE_OCID" 2>&1) || ATTACH_JSON=""
  if [ "$DEBUG" = "1" ]; then
    echo "  raw vnic-attachment list output:"
    echo "$ATTACH_JSON" | head -n 20 | sed 's/^/    /'
  fi
  VNIC_OCID=$(echo "$ATTACH_JSON" | jq -r '.data[0]."vnic-id" // .data[0].id // empty' 2>/dev/null || true)
  [ -n "$VNIC_OCID" ] && ok "VNIC (from vnic-attachment list): $VNIC_OCID"
fi

# Strategy 3: search all VNICs in the tenancy for one matching this instance
if [ -z "$VNIC_OCID" ]; then
  warn "vnic-attachment list returned nothing — searching all VNICs in tenancy"
  ALL_VNICS=$(oci network vnic list \
    --compartment-id "$COMPARTMENT_ID" \
    --query 'data[].{id:id,"display-name":"display-name"}' \
    --output json 2>&1)
  if [ "$DEBUG" = "1" ]; then
    echo "  all VNICs:"
    echo "$ALL_VNICS" | jq '.' 2>/dev/null | head -n 30 | sed 's/^/    /'
  fi
  # Pick the first VNIC for now (assumes only one VM, one VNIC)
  VNIC_OCID=$(echo "$ALL_VNICS" | jq -r '.data[0].id // empty' 2>/dev/null || true)
  [ -n "$VNIC_OCID" ] && ok "VNIC (from full VNIC list): $VNIC_OCID"
fi

# Strategy 4: brute-force grep the instance JSON for any ocid1.vnic... pattern
if [ -z "$VNIC_OCID" ]; then
  warn "falling back to grep on the instance JSON"
  VNIC_OCID=$(echo "$INSTANCE_JSON" | grep -oE 'ocid1\.vnic\.oc1\.[a-z0-9.-]+' | head -n 1 || true)
  [ -n "$VNIC_OCID" ] && ok "VNIC (from grep): $VNIC_OCID"
fi

[ -n "$VNIC_OCID" ] || die "All strategies failed. Set DEBUG=1 and re-run to see the raw output: DEBUG=1 bash <(curl -sSL https://raw.githubusercontent.com/barnymurt/trg-report/main/infra/oracle/find-or-attach-public-ip.sh)"

# ─── Step 5: get the private IP OCID from the VNIC ───────────────────
step "Fetching VNIC details (private IP OCID)…"
VNIC_JSON=$(oci network vnic get --vnic-id "$VNIC_OCID" 2>&1) || die "vnic get failed: $VNIC_JSON"

# Try several field paths for the private IP OCID (varies by CLI version)
PRIVATE_IP_OCID=$(echo "$VNIC_JSON" | jq -r '.data."primary-private-ip".id // .data."private-ip".id // empty' 2>/dev/null || true)
PRIVATE_IP=$(echo "$VNIC_JSON" | jq -r '.data."primary-private-ip"."ip-address" // .data."private-ip" // empty' 2>/dev/null || true)

# If still empty, list private IPs on this VNIC directly
if [ -z "$PRIVATE_IP_OCID" ]; then
  PRIV_IPS=$(oci network private-ip list \
    --compartment-id "$COMPARTMENT_ID" \
    --vnic-id "$VNIC_OCID" 2>&1) || PRIV_IPS=""
  if [ "$DEBUG" = "1" ]; then
    echo "  raw private-ip list:"
    echo "$PRIV_IPS" | head -n 20 | sed 's/^/    /'
  fi
  PRIVATE_IP_OCID=$(echo "$PRIV_IPS" | jq -r '.data[0].id // empty' 2>/dev/null || true)
  PRIVATE_IP=$(echo "$PRIV_IPS" | jq -r '.data[0]."ip-address" // empty' 2>/dev/null || true)
fi

[ -n "$PRIVATE_IP_OCID" ] || die "Could not determine private IP OCID. Re-run with DEBUG=1."

ok "vnic:        $VNIC_OCID"
ok "private IP:  $PRIVATE_IP"
ok "private IP OCID: $PRIVATE_IP_OCID"

# ─── Step 6: check if public IP already exists ───────────────────────
if [ -n "$EXISTING_PUBLIC_IP" ] && [ "$EXISTING_PUBLIC_IP" != "null" ]; then
  ok "instance already has a public IP: $EXISTING_PUBLIC_IP"
  PUBLIC_IP="$EXISTING_PUBLIC_IP"
else
  # ─── Step 7: create ephemeral public IP ─────────────────────────────
  step "Creating ephemeral public IPv4…"
  PUB_JSON=$(oci network public-ip create \
    --compartment-id "$COMPARTMENT_ID" \
    --lifetime EPHEMERAL \
    --display-name "trg-${INSTANCE_NAME}-public" 2>&1)
  PUB_EXIT=$?
  if [ "$PUB_EXIT" -ne 0 ]; then
    die "public-ip create failed: $PUB_JSON"
  fi
  PUBLIC_IP=$(echo "$PUB_JSON" | jq -r '.data."ip-address" // empty' 2>/dev/null || true)
  PUBLIC_IP_OCID=$(echo "$PUB_JSON" | jq -r '.data.id // empty' 2>/dev/null || true)
  if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" = "null" ]; then
    die "public-ip create returned no address: $PUB_JSON"
  fi
  ok "created: $PUBLIC_IP (ocid: $PUBLIC_IP_OCID)"

  # ─── Step 8: attach ─────────────────────────────────────────────────
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
echo -e "  \033[1mFrom your laptop (PowerShell):\033[0m"
echo ""
echo -e "  \033[1;36mssh -i \"C:\\Users\\bmurt\\Downloads\\ssh-key-2026-09-02.key\" opc@$PUBLIC_IP\033[0m"
echo ""
echo -e "  \033[1mIf 'opc' doesn't work, try 'ubuntu' — depends on the image.\033[0m"
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
echo -e "  \033[1mLast step — open these network ports in the OCI console:\033[0m"
echo -e "  Networking → VCN → Subnets → public subnet → Default Security List"
echo "  Add ingress rules: TCP 22, 80, 443, 7860 from 0.0.0.0/0"
echo ""
