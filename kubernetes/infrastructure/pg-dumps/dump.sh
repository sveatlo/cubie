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
  # kubectl exec can drop the end of stdout and still exit 0 (kubernetes/kubernetes#142376).
  # Compressing in the pod shrinks the stream, and the trailer check catches a cut that still happens.
  ok=0
  for attempt in 1 2 3; do
    if kubectl exec -n "$ns" "$primary" -c postgres -- sh -c 'pg_dumpall --clean --if-exists | gzip' > "$out.tmp" \
      && zcat "$out.tmp" | tail -n 5 | grep -q 'PostgreSQL database cluster dump complete'; then
      ok=1
      break
    fi
    echo "retry $ns/$name: attempt $attempt incomplete" >&2
  done

  if [ "$ok" = 1 ]; then
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
