# Day-Zero Bootstrap Runbook

Complete step-by-step guide to go from bare Proxmox VMs to a fully GitOps-managed cluster.

> **Important rules before you start:**
>
> - Never SSH into Talos nodes — all config is applied via `talosctl`
> - Never commit unencrypted secret files
> - `talosctl bootstrap` must be run **exactly once**, on the first control-plane node only

---

## Prerequisites

### 1. Install required tools on your workstation

```bash
# Homebrew (macOS) or equivalent
brew install talosctl kubectl helm sops age git

# Or on Arch Linux
paru -S talosctl kubectl helm sops age git
```

Minimum versions:
| Tool | Min version |
|------|-------------|
| talosctl | v1.7+ |
| kubectl | v1.29+ |
| helm | v3.14+ |
| sops | v3.8+ |
| age | v1.1+ |

---

## Phase 1: Secrets Setup

### 2. Generate age encryption key

```bash
age-keygen -o ~/.config/sops/age/keys.txt
```

Copy the **public key** from the output (line starting with `# public key:`).

### 3. Configure SOPS

Edit `.sops.yaml` at the repo root and replace `age1REPLACE_WITH_YOUR_AGE_PUBLIC_KEY` with your actual public key:

```bash
# Verify your key
cat ~/.config/sops/age/keys.txt
# public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

```bash
# Update .sops.yaml
sed -i 's/age1REPLACE_WITH_YOUR_AGE_PUBLIC_KEY/age1YOUR_ACTUAL_KEY/' .sops.yaml
```

---

## Phase 2: Talos Configuration

### 4. Customize node configuration

Edit per-node patches in `talos/nodes/` and `talos/patches/`:

```bash
# Set your cluster VIP (must be unused IP on your LAN)
editor talos/patches/controlplane/vip.yaml

# Add/edit per-node patches (hostname, IP, disk)
editor talos/nodes/cp-01.yaml
editor talos/nodes/worker-01.yaml
# Add more files for additional nodes (cp-02.yaml, worker-02.yaml, etc.)
```

### 5. Generate Talos cluster secrets

```bash
# Generate fresh PKI + bootstrap token
talosctl gen secrets -o talos/secrets.yaml.sops

# Encrypt with SOPS (removes plaintext automatically)
sops --encrypt -i talos/secrets.yaml.sops

# Commit the encrypted secrets
git add talos/secrets.yaml.sops .sops.yaml
git commit -m "chore: add encrypted talos secrets"
```

### 6. Generate machine configs

```bash
# Renders all node configs from patches + secrets into talos/configs/ (gitignored)
talos/scripts/gen-configs.sh

# Verify output
ls talos/configs/
# controlplane.yaml  cp-01.yaml  talosconfig  worker.yaml

# Set TALOSCONFIG for your shell session (talosconfig is gitignored, regenerate as needed)
export TALOSCONFIG=talos/configs/talosconfig

# Optional: merge into ~/.talos/config so you don't need to export every session
talosctl config merge talos/configs/talosconfig
```

### 7. Boot VMs and apply configs

Boot each Proxmox VM from the Talos ISO (metal image). Once the maintenance screen appears:

```bash
# Apply to each node (use --insecure on first boot before TLS is established)
talos/scripts/apply-configs.sh --insecure

# Or single node
talos/scripts/apply-configs.sh --insecure --node cp-01
```

---

## Phase 3: Bootstrap Kubernetes

### 8. Bootstrap etcd (run ONCE on first control-plane only)

Wait for the node to show `Booting` status, then:

```bash
# Get cp-01 IP from your node patch
CP01_IP=192.168.1.51   # Edit this

talosctl bootstrap \
  --nodes "$CP01_IP" \
  --endpoints "$CP01_IP"
```

Wait ~2-3 minutes for Kubernetes API server to become ready.

### 9. Fetch kubeconfig

```bash
hack/kubeconfig.sh
# Merges into ~/.kube/config

# Verify
kubectl cluster-info
kubectl get nodes
```

All nodes should eventually reach `Ready` status.

---

## Phase 4: GitOps Bootstrap

### 10. Add AWS Route53 credentials for cert-manager

```bash
# Create the plaintext secret (will be encrypted immediately)
cat > /tmp/route53-secret.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: route53-credentials
  namespace: cert-manager
stringData:
  secret-access-key: "REPLACE_WITH_YOUR_AWS_SECRET_KEY"
EOF

# Encrypt it in place
cp /tmp/route53-secret.yaml kubernetes/infrastructure/cert-manager/config/route53-secret.yaml
hack/edit-secret.sh kubernetes/infrastructure/cert-manager/config/route53-secret.yaml
# → creates route53-secret.yaml.sops
```

Also update the ClusterIssuer manifests with your actual domain and AWS account:

```bash
editor kubernetes/infrastructure/cert-manager/config/clusterissuer-staging.yaml
editor kubernetes/infrastructure/cert-manager/config/clusterissuer-prod.yaml
```

### 11. Update placeholder values

Fill in your real values in these files before committing:

| File                                                                 | What to update                     |
| -------------------------------------------------------------------- | ---------------------------------- |
| `kubernetes/infrastructure/metallb/config/ipaddresspool.yaml`        | Your LAN IP range for services     |
| `kubernetes/infrastructure/cert-manager/config/clusterissuer-*.yaml` | Domain, AWS region, hosted zone ID |
| `kubernetes/infrastructure/traefik/config/wildcard-cert.yaml`        | Your domain                        |
| `kubernetes/infrastructure/nfs-csi/config/storageclass.yaml`         | NFS server IP and share path       |

### 12. Install ArgoCD (bootstrap only)

```bash
bootstrap/argocd/install.sh
```

This installs ArgoCD via Helm and creates the `helm-secrets-private-keys` Secret from your age key.

### 13. Apply the root ApplicationSet

```bash
kubectl apply -f kubernetes/apps/applicationset.yaml
```

ArgoCD will now auto-discover and sync all components in `kubernetes/infrastructure/`.

### 14. Enable ArgoCD self-management

```bash
kubectl apply -f kubernetes/argocd/application.yaml
```

ArgoCD now manages itself from Git. Future changes to `kubernetes/argocd/values.yaml` are auto-applied.

---

## Phase 5: Verify

```bash
# Watch sync status
kubectl get applications -n argocd

# All should reach Synced / Healthy
# metallb → cert-manager → traefik → nfs-csi

# Check cert-manager issued the wildcard cert
kubectl get certificate -A

# Test ingress
curl -k https://traefik.<your-domain>
```

---

## Ongoing Operations

| Task             | Command                                                         |
| ---------------- | --------------------------------------------------------------- |
| Add a new app    | Create `kubernetes/apps/<name>/kustomization.yaml`, commit+push |
| Edit a secret    | `hack/edit-secret.sh <file.yaml.sops>`                          |
| Add a node       | Add `talos/nodes/<hostname>.yaml`, run gen-configs + apply      |
| Upgrade Talos    | Update image tag in node patch, run gen-configs + apply         |
| Fetch kubeconfig | `hack/kubeconfig.sh`                                            |
