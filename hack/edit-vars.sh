#!/usr/bin/env bash
# Edit the render-time substitution vars (domains) — thin wrapper over edit-secret.sh.
# First run encrypts vars/domains.yaml -> vars/domains.yaml.sops; later runs edit it.
# Usage: hack/edit-vars.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT/vars/domains.yaml.sops" ]]; then
  exec "$ROOT/hack/edit-secret.sh" "$ROOT/vars/domains.yaml.sops"
else
  exec "$ROOT/hack/edit-secret.sh" "$ROOT/vars/domains.yaml"
fi
