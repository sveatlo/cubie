---

Implementation Complete

All files created successfully. Verification results:

┌─────────────────────────────────────────────┬────────────────────────────────────────┐
│ Check │ Result │
├─────────────────────────────────────────────┼────────────────────────────────────────┤
│ git status │ No unencrypted secrets staged │
├─────────────────────────────────────────────┼────────────────────────────────────────┤
│ bash talos/scripts/gen-configs.sh --dry-run │ Passed — reads patches, lists nodes │
├─────────────────────────────────────────────┼────────────────────────────────────────┤
│ route53-secret.yaml.sops │ Placeholder .sops file (not plaintext) │
├─────────────────────────────────────────────┼────────────────────────────────────────┤
│ talos/secrets.yaml │ Does not exist (gitignored path) │
└─────────────────────────────────────────────┴────────────────────────────────────────┘

What was created

- .gitignore / .sops.yaml — excludes secrets, kubeconfig, talos/configs/; SOPS rules for age encryption
- README.md — stack overview and quick-start
- hack/ — decrypt-secret.sh, edit-secret.sh, kubeconfig.sh
- talos/patches/ — cluster-name, NTP, VIP, worker labels
- talos/nodes/ — cp-01.yaml, worker-01.yaml (example per-node patches)
- talos/scripts/ — gen-configs.sh (with --dry-run), apply-configs.sh
- bootstrap/README.md — complete 14-step day-zero runbook
- bootstrap/argocd/ — Helm values + install script (creates age key secret)
- kubernetes/apps/applicationset.yaml — root ApplicationSet with git+matrix generator
- kubernetes/infrastructure/ — MetalLB (wave 0), cert-manager (wave 0), Traefik (wave 1), NFS CSI (wave 2) — each with application.yaml, kustomization.yaml, values.yaml, config/
- kubernetes/argocd/ — self-management Application (multi-source Helm)
- CLAUDE.md — stack, layout, critical rules, workflows, node inventory table

Before first use

Search for REPLACE in the repo and fill in: your age public key (.sops.yaml), Git repo URL (all application.yaml files and ApplicationSet), domain name, AWS credentials, NFS server, and node IPs/disks.
