# cubie — Homelab Kubernetes IaC

GitOps-driven Kubernetes cluster running on Talos Linux (Proxmox VMs).

## Stack

| Layer | Tool |
|-------|------|
| OS | Talos Linux |
| CNI | Flannel (Talos built-in) |
| Load Balancer | MetalLB (Layer 2) |
| Ingress | Traefik (Helm) |
| TLS | cert-manager + Let's Encrypt + AWS Route53 DNS-01 |
| GitOps | ArgoCD (self-managed, ApplicationSets) |
| Storage | NFS CSI driver |
| Secrets | SOPS + age |

## Repository Layout

```
cubie/
├── .sops.yaml                    # SOPS encryption rules (age key reference)
├── talos/                        # Talos machine config patches + scripts
│   ├── patches/                  # Declarative patches applied to all nodes
│   ├── nodes/                    # Per-node patches (hostname, IP, disk)
│   └── scripts/                  # gen-configs.sh / apply-configs.sh
├── bootstrap/                    # Day-zero runbook + ArgoCD Helm install
│   ├── README.md                 # Step-by-step bootstrap guide ← START HERE
│   └── argocd/                   # Initial ArgoCD Helm values + install script
└── kubernetes/                   # All cluster state synced by ArgoCD
    ├── apps/                     # Root ApplicationSet + future workloads
    ├── argocd/                   # ArgoCD self-management manifests
    └── infrastructure/           # Platform components (ordered by sync-wave)
        ├── metallb/              # wave 0 — L2 load balancer
        ├── cert-manager/         # wave 0 — TLS automation
        ├── traefik/              # wave 1 — ingress + TLS termination
        └── nfs-csi/              # wave 2 — persistent storage
```

## Quick Start

See [`bootstrap/README.md`](bootstrap/README.md) for the complete day-zero runbook.

## Adding a New Application

1. Create `kubernetes/apps/<app-name>/` directory
2. Add `kustomization.yaml` (Helm release or plain manifests)
3. Add `values.yaml` if using Helm
4. Commit and push — ArgoCD ApplicationSet auto-discovers it

## Image Updates

Renovate tracks chart versions in `kustomization.yaml` separately from image versions:

- `helm-values` reads `values.yaml`, `*-values.yaml`, and `values-*.yaml`, including app-template `image.repository` / `image.tag` pairs.
- `kubernetes` reads container images in manifests under `kubernetes/`.
- Custom regex managers cover CNPG `imageName`, anchored images, Actions job-image URLs, and the Actions chart's standalone Docker-in-Docker tag.

Set an explicit release tag for each image declared in this repository. CI job images use dated tags within their existing Ubuntu release. Images inherited entirely from chart defaults remain chart-managed.

The package rules preserve Bookshelf's hardcover/softcover variant and Livrarr's alpha channel. They also exclude historical registry tags that would otherwise look newer than current Hermes, Lidarr, and qBittorrent releases.

Database and cluster upgrades need separate review: PostgreSQL stays on major 17, Immich's VectorChord image stays on PostgreSQL 16 with extension 0.4.x, and the backup job's kubectl stays on Kubernetes 1.35. Talos installer upgrades are outside these image managers.

With a supported Node.js version, validate the configuration and perform a read-only registry lookup:

```bash
npx --yes --package=renovate renovate-config-validator --strict
npx --yes --package=renovate renovate --platform=local --dry-run=lookup \
  --enabled-managers=helm-values,kubernetes,custom.regex
```

References: [Helm values manager](https://docs.renovatebot.com/modules/manager/helm-values/), [Kubernetes manager](https://docs.renovatebot.com/modules/manager/kubernetes/), [custom regex manager](https://docs.renovatebot.com/modules/manager/regex/).

## Managing Secrets

```bash
# Encrypt a new secret file
hack/edit-secret.sh kubernetes/infrastructure/cert-manager/config/route53-secret.yaml

# Decrypt for inspection (do not commit plaintext)
hack/decrypt-secret.sh kubernetes/infrastructure/cert-manager/config/route53-secret.yaml.sops
```

## Talos Config Regeneration

```bash
# After changing patches or adding a node:
talos/scripts/gen-configs.sh

# Apply to a specific node:
talosctl apply-config --nodes <IP> --file talos/configs/<hostname>.yaml
```
