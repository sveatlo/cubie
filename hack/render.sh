#!/usr/bin/env bash
# Render a component locally exactly like the ArgoCD repo-server CMP does:
#   substitute ${DOMAIN_x} in the source files, then kustomize build --enable-helm
# with substitution values decrypted from vars/domains.yaml.sops.
#
# Substitution happens on the SOURCE (before build) so domain values that helm
# base64-encodes into Secrets are also substituted — a post-render sed cannot reach
# inside base64. Done on a throwaway copy so the working tree is never mutated.
#
# Use this to preview manifests and to diff render-parity before/after templating.
# Usage: hack/render.sh <component-dir>      (defaults to current directory)
set -euo pipefail

DIR="${1:-.}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE

# Decrypt the vars file and load it as environment variables.
set -a
eval "$(sops -d "$ROOT/vars/domains.yaml.sops" \
  | sed -n -E 's/^([A-Za-z_][A-Za-z0-9_]*):[[:space:]]*(.*)$/\1=\2/p')"
set +a
: "${DOMAIN_0:?domain vars not decrypted}" "${DOMAIN_1:?domain vars not decrypted}"

# Build sed args from var NAMES so the literal ${DOMAIN_x} strings never appear here
# (matches the CMP, which must stay self-substitution safe). Keep this allowlist in
# sync with the CMP plugin in kubernetes/argocd/values.yaml.
args=()
for v in DOMAIN_0 DOMAIN_1; do
  eval "val=\${$v:?missing $v}"
  args+=(-e "s|\${$v}|$val|g")
done

# Copy the component to a temp dir, substitute in the source, then build there.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -a "$DIR/." "$work/"
find "$work" -type f \( -name '*.yaml' -o -name '*.yml' \) -not -path '*/charts/*' -print0 \
  | xargs -0 -r sed -i "${args[@]}"

if command -v kustomize >/dev/null 2>&1; then
  kustomize build --enable-helm "$work"
else
  kubectl kustomize --enable-helm "$work"
fi
