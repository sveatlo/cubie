#!/usr/bin/env bash
# Encrypt (or re-encrypt / edit in-place) a secret with SOPS.
# If the file does not end in .sops, it encrypts it to <file>.sops and removes the original.
# If the file already ends in .sops, it opens it for editing in $EDITOR.
# Usage: hack/edit-secret.sh <path/to/file.yaml[.sops]>
set -euo pipefail

FILE="${1:-}"
if [[ -z "$FILE" ]]; then
  echo "Usage: $0 <path/to/file.yaml[.sops]>" >&2
  exit 1
fi

SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE

if [[ "$FILE" == *.sops* ]]; then
  # Edit existing encrypted file
  sops "$FILE"
else
  # Encrypt new file
  ENCRYPTED="${FILE%.yaml}.yaml.sops"
  sops --encrypt "$FILE" > "$ENCRYPTED"
  echo "Encrypted: $ENCRYPTED"
  echo "Removing plaintext: $FILE"
  rm "$FILE"
fi
