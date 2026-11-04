# Hermes household instances

Samwise is the first household instance. The shared `base/` supplies the pinned Hermes runtime, dashboard Service, a dedicated PVC and initialization. Each directory under `instances/` supplies identity, configuration, hostname, resource suffix, selectors and Secret references.

| Setting | Samwise |
| --- | --- |
| Deployment / PVC | `ai/hermes-samwise` |
| Dashboard | `https://samwise.${DOMAIN_0}` |
| Authentik application | `Samwise (Hermes)`, slug `hermes-samwise` |
| Dashboard OAuth client | `hermes-dashboard-samwise`, public client with PKCE |
| Access group | `app_hermes_samwise`, initially only `sveatlo` |
| Telegram | Existing bot token, username, owner allowlist and home channel |
| Model | OpenAI subscription OAuth with a fresh sign-in, no paid API fallback |
| Integrations | Home Assistant administrator access and Rohlík MCP OAuth |

Separate Deployments, PVCs, ConfigMaps, Secrets and Authentik access keep instances' state apart. Hermes profiles alone are not the isolation boundary: the dashboard can administer profiles within its installation. This is not hostile-tenant isolation; the cluster and NFS administrators still control the data.

## Runtime and identity

Initialization installs the official Home Assistant plugin at commit `4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072` (version `2.0.1`) with dependency consent. A failed install blocks startup. The managed `config.yaml` is refreshed each start. `SOUL.md` is a seed: copied only if absent, so later runtime edits survive restarts. A new PVC gives Samwise a fresh identity, without inheriting old memories, conversations, skills or jobs.

Telegram, CLI and API toolsets contain terminal, file, Home Assistant and Rohlík tools, not browser tools. There is no browser or alert sidecar, GitHub credential helper, Kubernetes RBAC grant, projected service-account token, SSH key, Talos config, Proxmox credential or operator-tool download. The image still contains general-purpose software and network access; these changes do not make arbitrary terminal commands a sandbox.

The official HA plugin provides discovery and device-control tools. Its autonomous event platform stays disabled. The gateway also receives `HASS_URL` and `HASS_TOKEN` through the terminal credential override so it retains full REST/WebSocket administration, including operations the plugin restricts. The retained token belongs to the local-only HA administrator `Hermes` (`hermes`); its recorded expiry is 2027-11-02. Do not revoke it during this reset.

Samwise may perform requested routine lights, media and ordinary comfort adjustments. Its identity requires specific confirmation for locks, alarms, doors/gates, camera/privacy changes, hazardous appliances and HA configuration/automation edits. These are behavioral rules, not reduced token permissions.

The dashboard keeps native Authentik SSO as its sole login gate; its ingress is not LAN-filtered. The blueprint creates the instance group and owner membership, provisions the exact HTTPS callback, and removes the old `hermes` application/provider. Future family access requires an intentional update to the group membership in the blueprint and, separately, the Telegram allowlist.

## Secrets

Encrypted files are not Kustomize resources. Apply them manually at cutover:

```bash
hack/apply-secret.sh kubernetes/apps/ai/config/hermes-credentials-samwise.yaml.sops
hack/apply-secret.sh kubernetes/apps/ai/config/hermes-homeassistant-samwise.yaml.sops
```

The first Secret contains only the existing four Telegram settings. The second contains only the existing `HASS_URL` and `HASS_TOKEN`. No operator, GitHub or webhook credentials are copied. Do not restore the old `.env`.

OpenAI and Rohlík require fresh sign-ins. No OAuth files or other state are copied from the old PVC. Stop the old gateway before starting Samwise so two instances do not poll the same Telegram bot.

## Fresh reset: owner merges first

PR #207 prepared the reset with Samwise stopped. The Samwise overlay now requests one replica; the reusable base stays at zero. The Telegram and HA Secrets were manually applied on 2026-11-04. OpenAI and Rohlík still require fresh sign-ins after activation.

**The preparation PR starts a maintenance window when merged.** ArgoCD will prune the old Deployment, browser, alert receiver, RBAC and ingress. Samwise remains at `replicas: 0`. The old PVC is no longer managed and ArgoCD can prune it. Its NFS files remain because the PV uses `Retain`; the owner will delete those files manually.

1. Before merging, agree on the maintenance window. The owner handles manual deletion of old files and historical copies; this PR does not erase them.
2. The owner merges the preparation PR. Wait for the `ai`, `authentik` and `kube-prometheus-stack` Argo applications to sync. Verify the old Deployment and all its Pods are gone, Samwise has zero replicas, its new PVC is bound, the HA token is retained, and Alertmanager still has its default email receiver.
3. Apply the two new encrypted Secrets above. Check the Authentik blueprint succeeded, `app_hermes_samwise` contains only the owner, and the old application/provider no longer exist.
4. The owner merges the activation PR setting the Samwise overlay's `replicas` count to `1`. Do not use `kubectl scale` against Argo-managed replicas. Wait for initialization and dashboard readiness.
5. Sign in to OpenAI and Rohlík again using Hermes's authentication flows. Do not restore the old `auth.json`, `mcp-tokens/` or `.env`.
6. Run the runtime, integration and model checks below. Verify Rohlík connects and discovers tools without modifying a cart. Test dashboard login as the owner and denial for a nonmember. Send a new private Telegram conversation and check the Samwise personality. Confirm the fresh installation has no inherited memories, chats, jobs, skills, workspace or alert reports. The smoke/model checks themselves create new state; that is not inherited history.
7. Use Telegram Bot API `setMyName`, `setMyDescription` and `setMyShortDescription` to set Samwise's household identity. Keep the bot username, token and owner allowlist unchanged. Do not delete messages from Telegram.
8. The owner manually deletes the old files and historical copies below. No cleanup Pod, wipe script or new archive is provided.

### Deletion targets and remaining checks

Known old storage:

- PVC `ai/hermes`.
- PV `pvc-de8b4656-eb6f-4b5d-a286-50798533eff7`, reclaim policy `Retain`.
- NFS `10.69.10.3:/mnt/rapida/cubie`, subdirectory `ai/hermes/pvc-de8b4656-eb6f-4b5d-a286-50798533eff7`.

The owner will manually remove the contents of that old subdirectory, including its internal `backups/`, `.curator_backups/`, conversations, memories, skills, jobs, plugins, databases, logs, workspaces and credential copies. Recheck the exact path and confirm the old Pods are stopped before deletion. Deleting the PVC alone does not erase retained NFS data. The released PV can be removed after the directory has been erased; check whether ArgoCD already pruned the old PVC.

Delete the old live Secrets `ai/hermes-credentials`, `ai/hermes-homeassistant`, `ai/hermes-ssh`, `ai/hermes-talos` and `monitoring/hermes-alert-webhook` after confirming no remaining consumers. The HA token itself stays valid in `hermes-homeassistant-samwise`. Remove obsolete local setup helpers and any credential copies discovered during cutover; do not print their contents.

Revoke the former GitHub token upstream **only if it is dedicated to this agent**. Its sharing status has not been established. Remove local SSH, Talos and Proxmox credentials but leave those upstream credentials valid, as requested.

No Kubernetes VolumeSnapshots or Hermes backup CronJobs were found during inventory. The mounted `/mnt/nas/home/backup` appears to be a Borg repository; a bounded read-only archive-list attempt did not complete. NAS snapshots, offsite replication and selectively deletable historical archives remain **unverified**. Obtain access and identify the exact copies before deleting them. Never delete another application's archive or a shared snapshot to erase Hermes. If a shared immutable snapshot cannot be selectively cleaned, report its retention/access restrictions and obtain a decision; do not call the reset fully erased.

Encrypted operator Secrets remain in Git history. This reset removes their current files, not repository history, shared backups or upstream credential validity.

## Checks

Local checks:

```bash
python -m unittest discover -s kubernetes/apps/ai/hermes -p 'test_*.py' -v
kubectl kustomize kubernetes/apps/ai/hermes
hack/render.sh kubernetes/apps/ai
hack/render.sh kubernetes/apps/authentik
hack/render.sh kubernetes/infrastructure/kube-prometheus-stack
```

Post-activation checks, without device or shopping writes:

```bash
for check in runtime integrations model; do
  kubectl -n ai exec deployment/hermes-samwise -c gateway -- \
    /opt/hermes/.venv/bin/python /config/smoke_test.py "$check"
done
```

The integration check verifies Telegram and HA authentication only. Rohlík tool discovery, HA tool registration, SSO owner/nonmember access and Telegram behavior need separate verification; the local tests do not prove live authentication.

## Add another instance

Copy `instances/samwise/` to a new instance directory. Start its replica count at zero. Change the suffix, instance label, Secret references, hostname, OAuth issuer/client and identity; add the directory to the parent Kustomization. Create a separate Authentik group, application, provider and strict callback, and new encrypted Secrets. Use a different Telegram bot unless an explicit routing design replaces polling. Start with a fresh PVC and authorize that instance independently: do not clone Samwise's state or share rotating OAuth token files.

All instances start at zero replicas unless their overlay explicitly activates them. Never add a second instance without reviewing both rendered selectors and credential routing.

## References

- [Hermes v0.22.6 profiles and isolation limits](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/website/docs/user-guide/profiles.md)
- [Hermes v0.22.6 dashboard](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/website/docs/user-guide/features/web-dashboard.md)
- [Hermes v0.22.6 plugin installation](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/hermes_cli/plugins_cmd_install.py)
- [Pinned official Home Assistant plugin](https://github.com/NousResearch/hermes-official-plugins/tree/4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072/homeassistant)
- [Authentik blueprint structure](https://docs.goauthentik.io/customize/blueprints/v1/structure/)
- [Telegram Bot API profile methods](https://core.telegram.org/bots/api#setmyname)
