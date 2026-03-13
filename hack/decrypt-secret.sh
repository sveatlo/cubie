#!/usr/bin/env bash
# Decrypt a SOPS-encrypted file to stdout (does NOT write to disk).
# Usage: hack/decrypt-secret.sh <path/to/file.yaml.sops>
set -euo pipefail

FILE="${1:-}"
if [[ -z "$FILE" ]]; then
  echo "Usage: $0 <path/to/file.yaml.sops>" >&2
  exit 1
fi

if [[ ! -f "$FILE" ]]; then
  echo "Error: file not found: $FILE" >&2
  exit 1
fi

SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE

sops --decrypt "$FILE"
