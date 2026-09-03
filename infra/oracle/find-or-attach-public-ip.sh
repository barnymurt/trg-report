#!/usr/bin/env bash
# find-or-attach-public-ip.sh
#
# Paste this into OCI Cloud Shell (the >_ icon at the top right of the
# console). It will:
#   1. List all instances in your root compartment
#   2. For the one you select, find its primary VNIC + private IP
#   3. Create an ephemeral public IP (free) and print it
#   4. Tell you the SSH command to use from your laptop
#
# No credentials needed — Cloud Shell is already authenticated to your
# Oracle tenancy.

set -euo pipefail

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[0;32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[1;33m⚠\033[0m %s\n" "$1"; }
die()  { printf "  \033[0;31m✗\033[0m %s\n" "$1"; exit 1; }

# ─── Preflight ─────────────────────────────────────────────────────────
command -v oci >/dev/null 2>&1 || die "oci CLI not found in Cloud Shell — are you sure you're in Cloud Shell? (top right >_ icon)"

# Use the tenancy OCID as the compartment for queries. In Cloud Shell with
# InstancePrincipal auth, this works for the resources your user can see.
# If a more specific compartment env var is set, use that.
COMPARTMENT_ID="${OCI_COMPARTMENT:-$OCI_TENANCY}"
[ -n "$COMPARTMENT_ID" ] || die "Could not determine tenancy/compartment. Set OCI_COMPARTMENT=<ocid> and re-run."
ok "compartment: $COMPARTMENT_ID"

# ─── Step 1: list all instances ────────────────────────────────────────
step "Instances in your tenancy:"
oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query 'data[].{"display-name":"display-name",id:id,shape:shape,state:"lifecycle-state","public-ip":"public-ip",ocpu:"shape-config".ocpus,memory_gb:"shape-config"."memory-in-gbs"}' \
  --output table

# ─── Step 2: ask which one ─────────────────────────────────────────────
echo ""
INSTANCE_NAME=$(oci compute instance list --compartment-id "$COMPARTMENT_ID" --query 'data[0]."display-name"' --raw-output 2>/dev/null || true)

if [ -t 0 ]; then
  # interactive
  read -r -p "Which instance do you want a public IP on? (paste the name exactly, or just press Enter for: ${INSTANCE_NAME:-first one}): " INPUT_NAME
  INSTANCE_NAME="${INPUT_NAME:-$INSTANCE_NAME}"
fi

[ -n "$INSTANCE_NAME" ] || die "No instance name provided"

INSTANCE_OCID=$(oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query "data[?\"display-name\"=='$INSTANCE_NAME'].id | [0]" \
  --raw-output 2>/dev/null)

[ -n "$INSTANCE_OCID" ] || die "No instance found with name '$INSTANCE_NAME'"

ok "found instance: $INSTANCE_NAME"
ok "ocid: $INSTANCE_OCID"

# Check if a public IP is already assigned
EXISTING_IP=$(oci compute instance list \
  --compartment-id "$COMPARTMENT_ID" \
  --query "data[?id=='$INSTANCE_OCID'].\"public-ip\" | [0]" \
  --raw-output)

if [ -n "$EXISTING_IP" ] && [ "$EXISTING_IP" != "null" ]; then
  ok "instance already has a public IP: $EXISTING_IP"
  PUBLIC_IP="$EXISTING_IP"
else
  # ─── Step 3: find VNIC + private IP ───────────────────────────────────
  step "Finding primary VNIC and private IP…"
  VNIC_OCID=$(oci compute vnic list \
    --compartment-id "$COMPARTMENT_ID" \
    --instance-id "$INSTANCE_OCID" \
    --query 'data[?is-primary].id | [0]' \
    --raw-output)
  [ -n "$VNIC_OCID" ] || die "No primary VNIC found"

  PRIVATE_IP_OCID=$(oci network private-ip list \
    --compartment-id "$COMPARTMENT_ID" \
    --vnic-id "$VNIC_OCID" \
    --query 'data[0].id' \
    --raw-output)
  [ -n "$PRIVATE_IP_OCID" ] || die "No private IP found on VNIC"

  ok "vnic:  $VNIC_OCID"
  ok "priv:  $PRIVATE_IP_OCID"

  # ─── Step 4: create ephemeral public IP ──────────────────────────────
  step "Creating ephemeral public IPv4 address…"
  PUBLIC_IP=$(oci network public-ip create \
    --compartment-id "$COMPARTMENT_ID" \
    --lifetime EPHEMERAL \
    --display-name "trg-${INSTANCE_NAME}-public" \
    --query 'data.ip-address' \
    --raw-output)

  if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" = "null" ]; then
    die "public-ip create returned no address. Try: oci network public-ip create --compartment-id $COMPARTMENT_ID --lifetime EPHEMERAL --display-name trg-test"
  fi

  ok "created public IP: $PUBLIC_IP"

  # Attach to the VNIC's private IP
  step "Attaching public IP to the VNIC's private IP…"
  oci network public-ip update \
    --public-ip-id "$(oci network public-ip list \
        --compartment-id "$COMPARTMENT_ID" \
        --query "data[?\"ip-address\"=='$PUBLIC_IP'].id | [0]" \
        --raw-output)" \
    --private-ip-id "$PRIVATE_IP_OCID" \
    --force >/dev/null
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
