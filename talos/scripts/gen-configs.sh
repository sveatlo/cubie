#!/usr/bin/env bash
# Generate Talos machine configs from patches + encrypted secrets.
# Outputs configs to talos/configs/ (gitignored).
# Usage: talos/scripts/gen-configs.sh [--dry-run]
#
# Prerequisites:
#   - talosctl installed
#   - SOPS age key available (SOPS_AGE_KEY_FILE or default path)
#   - talos/secrets.yaml.sops decryptable
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TALOS_DIR="$REPO_ROOT/talos"
OUTPUT_DIR="$TALOS_DIR/configs"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
    --dry-run)
        DRY_RUN=true
        shift
        ;;
    *)
        echo "Unknown argument: $1" >&2
        exit 1
        ;;
    esac
done

# Read cluster config from patches
VIP=$(grep -E '^\s*name:' "$TALOS_DIR/patches/controlplane/vip.yaml" | awk '{print $2}' | head -1)
CLUSTER_NAME=$(grep -E '^\s+clusterName:' "$TALOS_DIR/patches/all/cluster-name.yaml" | awk '{print $2}' | head -1)

if [[ -z "$VIP" ]] || [[ -z "$CLUSTER_NAME" ]]; then
    echo "Error: could not read VIP or cluster name from patches." >&2
    exit 1
fi

echo "Cluster: $CLUSTER_NAME  Endpoint: https://$VIP:6443"

SECRETS_SOPS="$TALOS_DIR/secrets.yaml.sops"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] Would generate configs using secrets from $SECRETS_SOPS"
    echo "[dry-run] Patches:"
    echo "  all: $(ls "$TALOS_DIR/patches/all/"*.yaml 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
    echo "  controlplane: $(ls "$TALOS_DIR/patches/controlplane/"*.yaml 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
    echo "  workers: $(ls "$TALOS_DIR/patches/workers/"*.yaml 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
    echo "[dry-run] Nodes:"
    for NODE_PATCH in "$TALOS_DIR/nodes/"*.yaml; do
        echo "  $(basename "$NODE_PATCH")"
    done
    echo "[dry-run] Validation passed (patch files found)."
    exit 0
fi

# Decrypt secrets to a temp file (cleaned up on exit)
if [[ ! -f "$SECRETS_SOPS" ]]; then
    echo "Error: $SECRETS_SOPS not found. Run: talosctl gen secrets -o- > talos/secrets.yaml && hack/edit-secret.sh talos/secrets.yaml" >&2
    exit 1
fi

SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE

TMP_SECRETS=$(mktemp /tmp/talos-secrets.XXXXXX.yaml)
trap 'rm -f "$TMP_SECRETS"' EXIT

sops --decrypt "$SECRETS_SOPS" >"$TMP_SECRETS"

mkdir -p "$OUTPUT_DIR"

# Build patch args common to all nodes
COMMON_PATCHES=()
for f in "$TALOS_DIR/patches/all/"*.yaml; do
    COMMON_PATCHES+=(--config-patch "@$f")
done

CP_PATCHES=()
for f in "$TALOS_DIR/patches/controlplane/"*.yaml; do
    CP_PATCHES+=(--config-patch-control-plane "@$f")
done

WORKER_PATCHES=()
for f in "$TALOS_DIR/patches/workers/"*.yaml; do
    [[ -f "$f" ]] && WORKER_PATCHES+=(--config-patch-worker "@$f")
done

# Generate base configs (controlplane + worker templates)
talosctl gen config "$CLUSTER_NAME" "https://$VIP:6443" \
    --with-secrets "$TMP_SECRETS" \
    --output "$OUTPUT_DIR" \
    --output-types controlplane,worker,talosconfig \
    --force \
    "${COMMON_PATCHES[@]}" \
    "${CP_PATCHES[@]}" \
    "${WORKER_PATCHES[@]}"

echo "Base configs written to $OUTPUT_DIR/"

# Apply per-node patches on top of the generated base configs
for NODE_PATCH in "$TALOS_DIR/nodes/"*.yaml; do
    NODE=$(basename "$NODE_PATCH" .yaml)

    # Determine if node is controlplane or worker based on filename
    if [[ "$NODE" == cp-* ]]; then
        BASE="$OUTPUT_DIR/controlplane.yaml"
    else
        BASE="$OUTPUT_DIR/worker.yaml"
    fi

    OUT="$OUTPUT_DIR/$NODE.yaml"
    talosctl machineconfig patch "$BASE" \
        --patch "@$NODE_PATCH" \
        --output "$OUT"
    echo "  Generated: $OUT"
done

echo "Done. Apply with: talos/scripts/apply-configs.sh"
