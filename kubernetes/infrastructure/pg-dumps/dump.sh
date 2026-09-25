#!/bin/bash
set -euo pipefail

DEST=${DEST:-/dumps}
KEEP=3
STAMP=$(date +%F)
failed=0

clusters=$(kubectl get clusters.postgresql.cnpg.io -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace} {.metadata.name} {.status.currentPrimary}{"\n"}{end}')

while read -r ns name primary; do
  [ -n "$ns" ] || continue
  dir="$DEST/$ns/$name"
  out="$dir/$name-$STAMP.sql.gz"
  mkdir -p "$dir"

  # Exec'ing into the primary reaches postgres over the local socket, so no credentials are needed and every database and role is included.
  if kubectl exec -n "$ns" "$primary" -c postgres -- pg_dumpall --clean --if-exists | gzip > "$out.tmp" \
    && zcat "$out.tmp" | tail -n 5 | grep -q 'PostgreSQL database cluster dump complete'; then
    mv "$out.tmp" "$out"
    echo "ok   $ns/$name $(du -h "$out" | cut -f1)"
  else
    rm -f "$out.tmp"
    echo "FAIL $ns/$name" >&2
    failed=1
    continue
  fi

  ls -1t "$dir"/*.sql.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f
done <<< "$clusters"

exit "$failed"
