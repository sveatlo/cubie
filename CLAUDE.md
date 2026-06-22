# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# cubie homelab cluster

## Cluster Overview

**cubie** is a GitOps-driven Kubernetes homelab running on Talos Linux VMs in Proxmox.

| Layer | Tool | Notes |
|-------|------|-------|
| OS | Talos Linux | Immutable, API-only — no SSH |
| CNI | Flannel | Talos built-in, no chart needed |
| Load Balancer | MetalLB | Layer 2 / ARP, homelab LAN |
| Ingress | Traefik | Helm, HTTP→HTTPS redirect |
| TLS | cert-manager + Let's Encrypt | AWS Route53 DNS-01 |
| GitOps | ArgoCD | Self-managed, ApplicationSets |
| Storage | NFS CSI driver | Single NFS server |
| Database | CloudNativePG | Operator in infra, Clusters per-app |
| Monitoring | kube-prometheus-stack | Prometheus + Grafana + AlertManager |
| Auth | Authentik | OIDC/SAML IdP, CNPG-backed PostgreSQL |
| Secrets | SOPS + age | Only encrypted files in Git |

## Directory Layout

```
cubie/
├── .sops.yaml                        # Encryption rules — edit age public key here
├── .gitignore                        # Excludes secrets, kubeconfig, generated configs
├── hack/                             # Operator scripts
│   ├── decrypt-secret.sh             # sops --decrypt to stdout
│   ├── edit-secret.sh                # Encrypt new file or edit existing .sops file
│   └── kubeconfig.sh                 # Fetch + merge kubeconfig from cluster
├── talos/
│   ├── secrets.yaml.sops             # Encrypted cluster PKI + bootstrap token
│   ├── patches/all/                  # Applied to every node
│   ├── patches/controlplane/         # Applied to control-plane nodes only
│   ├── patches/workers/              # Applied to worker nodes only
│   ├── nodes/                        # Per-node patches: hostname, IP, disk
│   └── scripts/
│       ├── gen-configs.sh            # Renders full machine configs into talos/configs/
│       └── apply-configs.sh          # Applies configs via talosctl
├── bootstrap/
│   ├── README.md                     # Day-zero runbook <- START HERE for new cluster
│   └── argocd/
│       ├── install.sh                # Helm install + age key secret
│       └── values.yaml               # Bootstrap ArgoCD values
└── kubernetes/
    ├── apps/
    │   ├── applicationset.yaml       # Root ApplicationSet (apply once after ArgoCD)
    │   └── authentik/                # wave 3 — identity provider
    ├── argocd/                       # ArgoCD self-management
    └── infrastructure/               # Platform components, wave-ordered
        ├── metallb/                  # wave 0
        ├── cert-manager/             # wave 0
        ├── traefik/                  # wave 1
        ├── nfs-csi/                  # wave 2
        ├── cnpg/                     # wave 2 — CloudNativePG operator
        └── kube-prometheus-stack/    # wave 3
```

## Per-Component File Pattern

Every component under `kubernetes/infrastructure/` or `kubernetes/apps/` follows this structure:

```
<component>/
├── application.yaml          # ArgoCD Application with sync-wave annotation
├── kustomization.yaml        # Kustomize manifest: helmCharts + resources
├── values.yaml               # Helm values for the chart
└── config/                   # Extra K8s resources (secrets, CRs, alerts, dashboards)
    ├── *.yaml                # Plain manifests listed in kustomization.yaml resources
    ├── *.yaml.sops           # SOPS-encrypted secrets (NOT listed in kustomization.yaml)
    └── dashboards/*.json     # Grafana dashboards exposed via configMapGenerator
```

Key details:
- Helm charts are declared via Kustomize `helmCharts` field (not HelmRelease CRDs).
- SOPS-encrypted secrets live in `config/` but are **not** referenced in `kustomization.yaml` — they must be manually decrypted and applied to the cluster.
- Grafana dashboards use `configMapGenerator` with label `grafana_dashboard: "1"` for sidecar auto-discovery.
- The root `ApplicationSet` (`kubernetes/apps/applicationset.yaml`) auto-discovers all directories and creates ArgoCD Applications. No manual Application registration needed.

## Critical Rules

1. **Never SSH into Talos nodes.** All configuration is applied via `talosctl`.
2. **Never commit unencrypted secrets.** Always use `hack/edit-secret.sh` to encrypt before committing.
3. **`talosctl bootstrap` runs exactly once** — on cp-01 only, when etcd is first initialized.
4. **`talos/configs/` is gitignored** — regenerate with `talos/scripts/gen-configs.sh` on demand.
5. **Edit `.sops.yaml` before generating any secrets** — set your actual age public key.

## Common Workflows

### Add a new application
```bash
mkdir -p kubernetes/apps/<app-name>
# Add kustomization.yaml and values.yaml
git add kubernetes/apps/<app-name>/
git commit -m "feat: add <app-name>" && git push
# ArgoCD ApplicationSet auto-discovers and syncs it
```

### Add / rotate a secret
```bash
# Encrypt a new file (removes plaintext after encrypting)
hack/edit-secret.sh kubernetes/path/to/secret.yaml

# Edit an existing encrypted secret
hack/edit-secret.sh kubernetes/path/to/secret.yaml.sops
```

### Regenerate Talos machine configs
```bash
talos/scripts/gen-configs.sh
talos/scripts/apply-configs.sh --node <hostname>
# First boot: talos/scripts/apply-configs.sh --insecure
```

### Fetch kubeconfig
```bash
hack/kubeconfig.sh
```

## Node Inventory

| Hostname | Role | IP | Proxmox VM ID | Disk |
|----------|------|----|---------------|------|
| cp-01 | control-plane + worker | | | |

_Single-node cluster: cp-01 runs both control-plane and workloads (`allowSchedulingOnControlPlanes: true`). Fill in IP/VM ID/disk when provisioned._

## Network & Domains

- **LAN subnet:** `10.69.0.0/16`
- **MetalLB pool:** `10.69.11.1–10.69.11.199` (Layer 2 / ARP)
- **Traefik LB IP:** `10.69.11.42`
- **NFS server:** `10.69.10.3`
- **Wildcard certs:** `*.mirkwood.casa`, `*.vunder.io` (cert-manager, Route53 DNS-01)
- **Ingress pattern:** Standard Kubernetes Ingress with `ingressClassName: traefik` and Traefik annotations. LAN-only middleware: `traefik-lan-only@kubernetescrd`.

## Required Tools

| Tool | Install |
|------|---------|
| talosctl | `brew install talosctl` |
| kubectl | `brew install kubectl` |
| helm | `brew install helm` |
| sops | `brew install sops` |
| age | `brew install age` |

## Sync Wave Order

| Wave | Component | Why |
|------|-----------|-----|
| -1 | ArgoCD self-management | Must be healthy before everything |
| 0 | MetalLB | LoadBalancer IPs needed by Traefik |
| 0 | cert-manager | TLS needed by Traefik wildcard cert |
| 1 | Traefik | Depends on MetalLB (IP) + cert-manager (cert) |
| 2 | NFS CSI | Storage for workloads |
| 2 | CNPG operator | Database operator CRDs needed by apps |
| 2 | Node Feature Discovery | Auto-labels nodes with hardware features |
| 3 | kube-prometheus-stack | Monitoring after infra is ready |
| 3+ | Apps (authentik, etc.) | Workloads requiring the platform |
