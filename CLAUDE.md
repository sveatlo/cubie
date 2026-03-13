# CLAUDE.md — cubie homelab cluster

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
    │   └── applicationset.yaml       # Root ApplicationSet (apply once after ArgoCD)
    ├── argocd/                       # ArgoCD self-management
    └── infrastructure/               # Platform components, wave-ordered
        ├── metallb/                  # wave 0
        ├── cert-manager/             # wave 0
        ├── traefik/                  # wave 1
        └── nfs-csi/                  # wave 2
```

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
| cp-01 | control-plane | | | |
| worker-01 | worker | | | |

_Fill in this table as nodes are provisioned._

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
| 3+ | Apps | Workloads requiring the platform |
