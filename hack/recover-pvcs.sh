#!/usr/bin/env bash
# Full PVC recovery after ArgoCD outage.
# Deletes stuck pods → waits for PVCs to terminate → clears PV claimRefs →
# pre-creates every PVC pointing at its original PV so no empty volumes are
# provisioned. One PVC per (namespace, name): most-recent Bound PV wins for
# duplicates. PVs already gone from etcd are skipped (unrecoverable).
#
# Run ONCE after auto-sync is disabled and the revert is pushed.
# Safe to re-run: kubectl apply is idempotent.
set -euo pipefail

echo "=== Step 1: delete stuck pods to release PVC finalizers ==="
for ns in ai arr audiobookshelf authentik babybuddy bitcoin crowdsec \
           immich jellyfin kube-prometheus-stack mealie monitoring \
           nextcloud paperless; do
  kubectl delete pods -n "$ns" --all --grace-period=0 --force 2>/dev/null \
    && echo "  $ns: pods deleted" || true
done

echo ""
echo "=== Step 2: wait for all Terminating PVCs to finish ==="
echo "  (30-120s while Kubernetes cleans up)"
while kubectl get pvc -A --no-headers 2>/dev/null | grep -q Terminating; do
  printf "."
  sleep 3
done
echo ""
echo "  All PVCs terminated."

echo ""
echo "=== Step 3: clear claimRefs on Released PVs ==="
for pv in $(kubectl get pv --no-headers 2>/dev/null | awk '$5 == "Released" {print $1}'); do
  kubectl patch pv "$pv" --type=json \
    -p '[{"op":"remove","path":"/spec/claimRef"}]' 2>/dev/null \
    && echo "  cleared: $pv" || echo "  skip: $pv"
done

echo ""
echo "=== Step 4: pre-create PVCs bound to original PVs ==="
# Format: "ns  pvc-name  pv-name  capacity  accessMode"
# For duplicate PV entries per PVC name, only the most-recent Bound PV is kept.
# PVs missing from etcd (n8n-main-persistence/pvc-fdb3c37e, readarr/pvc-67831906)
# are excluded — the PV object is gone and cannot be recovered.

apply_pvc() {
  local ns="$1" name="$2" pv="$3" cap="$4" mode="$5"
  # Verify PV still exists before creating the PVC
  if ! kubectl get pv "$pv" &>/dev/null; then
    echo "  SKIP $ns/$name — PV $pv not found in cluster"
    return
  fi
  kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${name}
  namespace: ${ns}
spec:
  accessModes: ["${mode}"]
  resources:
    requests:
      storage: ${cap}
  storageClassName: nfs
  volumeName: ${pv}
EOF
  echo "  applied: $ns/$name → $pv"
}

# ai
apply_pvc ai ai-pipelines    pvc-54fe6468-da51-46fe-9c86-cbc0e69eab4a  2Gi   ReadWriteOnce
apply_pvc ai ai-open-webui   pvc-56f77b6d-7345-4265-9402-2a1ae622b739  10Gi  ReadWriteOnce
apply_pvc ai ollama          pvc-8f14bed0-7354-45ea-833f-df29bc32eb0c  30Gi  ReadWriteOnce
apply_pvc ai n8n-db-1        pvc-83267007-3363-4b27-90dd-69fb712bb34c  5Gi   ReadWriteOnce

# arr
apply_pvc arr bazarr                  pvc-dd7ab9de-0698-4fac-aeeb-4989f7435471  1Gi  ReadWriteOnce
apply_pvc arr bookshelf               pvc-c69db28c-07cb-4c60-8c00-111fd1b70f2f  2Gi  ReadWriteOnce
apply_pvc arr flaresolverr            pvc-2d007908-3b2d-4a6c-b7b1-ea35e1a22c14  1Gi  ReadWriteOnce
apply_pvc arr lidarr                  pvc-cf596874-3a2d-4c07-8064-944c07226360  2Gi  ReadWriteOnce
apply_pvc arr livrarr                 pvc-f46b1683-cae3-4878-b4d7-93092b472667  2Gi  ReadWriteOnce
apply_pvc arr prowlarr                pvc-03db3546-14d5-4274-aa53-87b47cc3be96  1Gi  ReadWriteOnce
apply_pvc arr qbittorrent             pvc-98e7e1de-d862-4f9a-9008-1baf7b6f084f  2Gi  ReadWriteOnce
apply_pvc arr radarr                  pvc-37cac76c-7528-42f5-b6b1-d47f31841175  2Gi  ReadWriteOnce
apply_pvc arr seerr-seerr-chart-config pvc-41416092-47cc-490a-8492-080d80026da2 5Gi  ReadWriteOnce
apply_pvc arr sonarr                  pvc-2292c4a4-b37d-413d-a439-0cb9a9f2dadf  2Gi  ReadWriteOnce
# readarr/pvc-67831906 excluded — PV missing from etcd

# audiobookshelf
apply_pvc audiobookshelf audiobookshelf-config   pvc-9612835a-e1bb-46fd-96b7-4b2785b2050b  1Gi  ReadWriteOnce
apply_pvc audiobookshelf audiobookshelf-metadata pvc-0b08eb3d-5496-4a10-97c0-3b156cae1adc  1Gi  ReadWriteOnce

# authentik
apply_pvc authentik authentik-db-1 pvc-15e1a2c0-39b9-47b9-a198-277511d8a2f5  5Gi  ReadWriteOnce

# babybuddy
apply_pvc babybuddy babybuddy      pvc-6856ec32-ff71-4562-b26b-c7bd5feaaf69  5Gi  ReadWriteOnce
apply_pvc babybuddy babybuddy-db-1 pvc-a4d4ae22-860c-48c4-8750-887a16a747e5  5Gi  ReadWriteOnce

# bitcoin
apply_pvc bitcoin data-bitcoind-0 pvc-4c95186d-6741-4013-bb9b-3be6462be487  50Gi  ReadWriteOnce
apply_pvc bitcoin data-lnd-0      pvc-c31400fd-d828-4946-9c42-6b9c4c4c3547  5Gi   ReadWriteMany

# crowdsec (app removed from ArgoCD but namespace + data still exist)
apply_pvc crowdsec crowdsec-db-pvc     pvc-4ab10a7a-067b-4478-8f58-ea5bf05961a7  1Gi  ReadWriteOnce
apply_pvc crowdsec crowdsec-config-pvc pvc-0ea7ca62-e6a3-41e8-a55a-5993013ff9e6  1Gi  ReadWriteOnce

# immich — immich-db-1 has 5 historical PVs; pvc-292614bc was most recently Bound
apply_pvc immich immich-db-1            pvc-292614bc-486e-4afd-a9ba-f9d04341cae5  16Gi  ReadWriteOnce
apply_pvc immich immich-library         pvc-8ede85ca-9851-4438-b9a6-cb713e36d233  2Ti   ReadWriteMany
apply_pvc immich immich-machine-learning pvc-30256b22-fae3-4336-b16e-30a4b0438cf8 10Gi  ReadWriteOnce
apply_pvc immich immich-valkey          pvc-73775b6e-12bf-4708-a013-ec12d565def9  1Gi   ReadWriteOnce

# jellyfin
apply_pvc jellyfin jellyfin-config pvc-2451781d-07b4-44b9-b0ff-81df07407cc5  5Gi  ReadWriteOnce

# mealie
apply_pvc mealie mealie      pvc-03e69b5e-8317-498e-be00-e93d5b7ad6b0  10Gi  ReadWriteOnce
apply_pvc mealie mealie-db-1 pvc-a67bac10-4cf5-495d-b49d-e79018596870  5Gi   ReadWriteOnce

# monitoring — prometheus has 3 PVs; pvc-15c75fc4 was most recently Bound
apply_pvc monitoring kube-prometheus-stack-grafana \
  pvc-dd68c35d-1803-45d3-9ad9-e3cdc731fb38  10Gi  ReadWriteOnce
apply_pvc monitoring \
  alertmanager-kube-prometheus-stack-alertmanager-db-alertmanager-kube-prometheus-stack-alertmanager-0 \
  pvc-506c9903-9154-4484-bdaf-740b2306df3d  5Gi  ReadWriteOnce
apply_pvc monitoring \
  prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0 \
  pvc-15c75fc4-527f-4553-94ed-3f42958ecaf2  50Gi  ReadWriteOnce

# nextcloud — nextcloud-db-1 PV pvc-b0329bc4 is Released (CNPG recreates it)
apply_pvc nextcloud nextcloud-db-1                    pvc-b0329bc4-1be7-40b2-94b8-65bc747dd0d7  5Gi    ReadWriteOnce
apply_pvc nextcloud nextcloud-nextcloud                pvc-8739db0c-0fae-4d7a-aa21-e56e26e7c35b  100Gi  ReadWriteMany
apply_pvc nextcloud redis-data-nextcloud-redis-master-0    pvc-486865a9-c584-4159-ab28-c790ce27a26a  8Gi  ReadWriteOnce
apply_pvc nextcloud redis-data-nextcloud-redis-replicas-0  pvc-9d0ee409-fb5a-4661-9b0b-cf99d7cb130d  8Gi  ReadWriteOnce
apply_pvc nextcloud redis-data-nextcloud-redis-replicas-1  pvc-05575f58-3fe4-4a35-af55-9f87499dd9d9  8Gi  ReadWriteOnce
apply_pvc nextcloud redis-data-nextcloud-redis-replicas-2  pvc-4933bfe0-4ab4-42a7-a40d-37517a2f344f  8Gi  ReadWriteOnce

# paperless
apply_pvc paperless paperless-consume pvc-b2b9df6a-c350-4370-9c8a-473ce2ca5cdf  5Gi   ReadWriteOnce
apply_pvc paperless paperless-data    pvc-b22a36fb-1139-4d1a-9cdc-9beb4bbb5e40  5Gi   ReadWriteOnce
apply_pvc paperless paperless-db-1   pvc-54520df7-07c9-44ba-a3ed-e61266805d76  5Gi   ReadWriteOnce
apply_pvc paperless paperless-export  pvc-a2442467-dd44-450b-b8c1-f9eeeed196df  10Gi  ReadWriteOnce
apply_pvc paperless paperless-media   pvc-d40660ab-b4ef-435d-90bd-9d6a6a79282c  50Gi  ReadWriteOnce

echo ""
echo "=== Step 5: verify all PVCs Bound ==="
sleep 8
echo "--- Bound ---"
kubectl get pvc -A --no-headers | awk '$3 == "Bound" {print $3, $1, $2, $4}' | sort
echo ""
echo "--- NOT Bound (investigate these) ---"
kubectl get pvc -A --no-headers | awk '$3 != "Bound" {print $3, $1, $2, $4}' | sort || echo "(none)"

echo ""
echo "=== Done ==="
echo "Skipped (PV missing from etcd — data unrecoverable):"
echo "  ai/n8n-main-persistence  pvc-fdb3c37e-e6fc-4256-9e0a-966138a07332"
echo "  arr/readarr              pvc-67831906-5193-4d3d-a7be-713b4f1f9ae6"
echo ""
echo "Re-enable sync per app once PVCs are Bound, e.g.:"
echo "  kubectl patch application jellyfin -n argocd --type=merge \\"
echo "    -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"prune\":true,\"selfHeal\":true}}}}'"
