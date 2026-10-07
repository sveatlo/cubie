# Local AI

Ollama serves `deepseek-r1:8b` over cluster DNS. Open WebUI uses Authentik sign-in
at `chat.${DOMAIN_0}`. The WebUI chart also runs Pipelines and Redis.

## Restore after removal

The PVC patches bind the three existing NFS volumes rather than creating empty
storage. Their old claim references must be cleared once before the restored
claims can bind. Check that each PV is still `Released` and belongs to `ai`:

```bash
kubectl get pv \
  pvc-8f14bed0-7354-45ea-833f-df29bc32eb0c \
  pvc-56f77b6d-7345-4265-9402-2a1ae622b739 \
  pvc-54fe6468-da51-46fe-9c86-cbc0e69eab4a
```

Only for those released volumes:

```bash
for pv in \
  pvc-8f14bed0-7354-45ea-833f-df29bc32eb0c \
  pvc-56f77b6d-7345-4265-9402-2a1ae622b739 \
  pvc-54fe6468-da51-46fe-9c86-cbc0e69eab4a; do
  kubectl patch pv "$pv" --type=merge -p '{"spec":{"claimRef":null}}'
done
kubectl create namespace ai --dry-run=client -o yaml | kubectl apply -f -
hack/apply-secret.sh kubernetes/apps/ai/config/ai-oidc-secret.yaml.sops
hack/apply-secret.sh kubernetes/apps/ai/config/ai-webui-secret.yaml.sops
```

ArgoCD discovers this directory after the commits reach remote master.
The Authentik Open WebUI provider must still exist and accept the restored client
credentials. Ollama requests 8Gi of RAM, so remove Klerigo before expecting it to
schedule on the current nodes. The former `talos-891-uxr` node pin is gone.
