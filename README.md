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
