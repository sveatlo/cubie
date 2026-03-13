#!/usr/bin/env bash
# Fetch kubeconfig from Talos cluster and merge into ~/.kube/config.
# Usage: hack/kubeconfig.sh [--endpoint <host-or-ip>]
#   Defaults to the VIP/endpoint defined in talos/patches/controlplane/vip.yaml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENDPOINT="${1:-}"
if [[ -z "$ENDPOINT" ]]; then
  # Try to read VIP from patch
  VIP_PATCH="$REPO_ROOT/talos/patches/controlplane/vip.yaml"
  if [[ -f "$VIP_PATCH" ]]; then
    ENDPOINT=$(grep -E '^\s+ip:' "$VIP_PATCH" | awk '{print $2}' | head -1)
  fi
fi

if [[ -z "$ENDPOINT" ]]; then
  echo "Error: could not determine cluster endpoint. Pass it as first argument." >&2
  exit 1
fi

echo "Fetching kubeconfig from $ENDPOINT ..."
talosctl kubeconfig \
  --nodes "$ENDPOINT" \
  --endpoints "$ENDPOINT" \
  --merge \
  "$HOME/.kube/config"

echo "Done. Test with: kubectl cluster-info"
