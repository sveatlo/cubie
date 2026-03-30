#!/usr/bin/env bash
# Bootstrap ArgoCD via Helm.
# Run once after cluster is up and kubeconfig is configured.
# After this, ArgoCD manages itself from kubernetes/argocd/ in Git.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ARGOCD_NAMESPACE="argocd"
ARGOCD_HELM_REPO="https://argoproj.github.io/argo-helm"
ARGOCD_CHART_VERSION="${ARGOCD_CHART_VERSION:-9.4.17}"  # pin for reproducibility

echo "=== ArgoCD Bootstrap ==="
echo "Chart version: $ARGOCD_CHART_VERSION"
echo "Namespace: $ARGOCD_NAMESPACE"
echo ""

# Ensure age key is available
AGE_KEYS_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
if [[ ! -f "$AGE_KEYS_FILE" ]]; then
  echo "Error: age keys file not found at $AGE_KEYS_FILE" >&2
  echo "Generate one with: age-keygen -o $AGE_KEYS_FILE" >&2
  exit 1
fi

# Create namespace
kubectl create namespace "$ARGOCD_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Create secret for SOPS age key (used by helm-secrets plugin in repo-server)
kubectl create secret generic helm-secrets-private-keys \
  --namespace "$ARGOCD_NAMESPACE" \
  --from-file=key.txt="$AGE_KEYS_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Created helm-secrets-private-keys secret"

# Add Argo Helm repo
helm repo add argo "$ARGOCD_HELM_REPO" --force-update
helm repo update argo

# Install/upgrade ArgoCD
helm upgrade --install argocd argo/argo-cd \
  --namespace "$ARGOCD_NAMESPACE" \
  --version "$ARGOCD_CHART_VERSION" \
  --values "$SCRIPT_DIR/values.yaml" \
  --wait \
  --timeout 5m

echo ""
echo "=== ArgoCD installed successfully ==="
echo ""
echo "Get initial admin password:"
echo "  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
echo ""
echo "Next steps:"
echo "  1. kubectl apply -f $REPO_ROOT/kubernetes/apps/applicationset.yaml"
echo "  2. kubectl apply -f $REPO_ROOT/kubernetes/argocd/application.yaml"
echo ""
echo "ArgoCD UI will be available after Traefik syncs (or port-forward):"
echo "  kubectl port-forward svc/argocd-server -n argocd 8080:80"
