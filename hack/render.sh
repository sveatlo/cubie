#!/usr/bin/env bash
# Render a component locally exactly like the ArgoCD repo-server CMP does:
#   kustomize build --enable-helm <dir> | envsubst '<allowlist>'
# with substitution values decrypted from vars/domains.yaml.sops.
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

# Substitute the allowlisted placeholders with sed (one pattern per variable).
# Mirrors the ArgoCD CMP generate command. Patterns are built from var NAMES so the
# literal ${DOMAIN_x} strings never appear here (matches the CMP, which must stay
# self-substitution safe). Keep this allowlist in sync with the CMP plugin.
substitute() {
  local args=() v val
  for v in DOMAIN_0 DOMAIN_1; do
    eval "val=\${$v:?missing $v}"
    args+=(-e "s|\${$v}|$val|g")
  done
  sed "${args[@]}"
}

# Prefer standalone kustomize; fall back to the kubectl built-in.
if command -v kustomize >/dev/null 2>&1; then
  kustomize build --enable-helm "$DIR" | substitute
else
  kubectl kustomize --enable-helm "$DIR" | substitute
fi
