# Hermes household instances

Samwise is the first household instance. The shared `base/` supplies the pinned Hermes runtime, Camofox sidecar, dashboard/browser Services, separate runtime/browser PVCs and initialization. Each directory under `instances/` supplies identity, configuration, hostname, resource suffix, selectors and Secret references.

| Setting | Samwise |
| --- | --- |
| Deployment / PVC | `ai/hermes-samwise` |
| Dashboard | `https://samwise.${DOMAIN_0}` |
| Browser desktop | `https://samwise-browser.${DOMAIN_0}/vnc.html?autoconnect=true&resize=remote` |
| Browser PVC | `ai/hermes-browser-samwise` |
| Authentik application | `Samwise (Hermes)`, slug `hermes-samwise` |
| Dashboard OAuth client | `hermes-dashboard-samwise`, public client with PKCE |
| Access group | `app_hermes_samwise`, initially only `sveatlo` |
| Telegram | Existing bot token, username, owner allowlist and home channel |
| Model | OpenAI subscription OAuth with a fresh sign-in, no paid API fallback |
| Integrations | Home Assistant administrator access, Rohlík MCP OAuth and Mealie MCP |

Separate Deployments, PVCs, ConfigMaps, Secrets and Authentik access keep instances' state apart. Hermes profiles alone are not the isolation boundary: the dashboard can administer profiles within its installation. This is not hostile-tenant isolation; the cluster and NFS administrators still control the data.

## Runtime and identity

Initialization installs the official Home Assistant plugin at commit `4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072` (version `2.0.1`) and Camofox plugin at commit `1138f25c8b7b5a8fb882b3161e248f29abbd1a46` (version `1.1.0`), with dependency consent. A failed install blocks startup. The managed `config.yaml` is refreshed each start. `SOUL.md` is a seed: copied only if absent, so later runtime edits survive restarts. A new PVC gives Samwise a fresh identity, without inheriting old memories, conversations, skills or jobs.

Telegram, CLI and API toolsets contain terminal, file, Home Assistant, Rohlík, Mealie and Camofox tools. There is no alert sidecar, GitHub credential helper, Kubernetes RBAC grant, projected service-account token, SSH key, Talos config, Proxmox credential or operator-tool download. The image still contains general-purpose software and network access; these changes do not make arbitrary terminal commands a sandbox.

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

## Mealie

Samwise uses `djwmarcx/better-mealie-mcp:3.30.0`, pinned by image digest to match Mealie v3.30.0. Renovate's Kubernetes manager tracks this image and its digest. A package-specific versioning rule also treats upstream `-r2`, `-r3`, etc. revisions as stable build updates rather than separate compatibility channels. All 283 tools are exposed, including administrative endpoints. Actual permissions come from the API token's account; this instance deliberately uses a separately named token from the owner's existing account. Revoking that token does not require changing the owner's password.

The MCP runs as a Kubernetes native sidecar in Samwise's Pod. Its startup probe must pass before the gateway starts. It listens on `127.0.0.1:8000/mcp`, with no Service or ingress, and calls `http://mealie.mealie.svc.cluster.local:9000`. It receives no Hermes PVC or configuration mount. Only this sidecar receives `MEALIE_API_TOKEN`, from the dedicated `ai/hermes-mealie-samwise` Secret; the gateway accesses Mealie through MCP rather than receiving its token directly. The sidecar has a read-only root filesystem and a small temporary volume.

Mealie tools are available to Telegram, CLI and dashboard/API sessions. Hermes's default tool-search behavior defers MCP schemas until needed. The full tool inventory remains available; long names are shortened by Hermes to fit provider limits. Listing tools alone does not prove the API token works.

Before merging the integration or rotating its token:

1. Create a separately named token under Mealie's Profile → Manage API Tokens (`/user/profile/api-tokens`). The account must have the permissions Samwise needs; this token has no independent API scopes.
2. Store it in the SOPS-encrypted `kubernetes/apps/ai/config/hermes-mealie-samwise.yaml.sops`, Secret `ai/hermes-mealie-samwise`, key `MEALIE_API_TOKEN`. Use `hack/edit-secret.sh`; never commit plaintext or add it to the Telegram/Home Assistant Secrets.
3. Apply it before the owner merges the integration:

   ```bash
   hack/apply-secret.sh kubernetes/apps/ai/config/hermes-mealie-samwise.yaml.sops
   ```

The initial dedicated Secret was applied on 2026-11-04, and a read-only `/api/users/self` request verified its authentication and administrative/food-organization permissions. The integration still requires an owner merge and post-sync MCP discovery/read verification. A missing Secret or failed sidecar startup blocks Samwise's rollout; do not merge before provisioning it. A separate instance needs its own token and Secret reference.

## Camofox browsing

Camofox `1.18.1` is pinned by image digest and starts as a native sidecar before Hermes initialization. The upstream image stores its browser under root-only `/root`, so a capability-free root init container copies the bundle into an ephemeral volume. The browser then runs as UID/GID `10000`, with a read-only root filesystem and bundle. It receives neither the Hermes PVC nor its Secrets. Its REST API (`9377`) and native VNC (`5900`) bind to loopback; only noVNC (`6080`) has a ClusterIP Service. Loopback is a Pod boundary, not a gateway credential boundary: any container in this Pod can control the browser. Other cluster workloads and cluster administrators can reach the internal noVNC Service; there is no hostile-workload isolation or VNC password.

The external noVNC ingress requires both the LAN allowlist and Authentik forward auth. It has a separate `hermes-samwise-browser` application bound to the existing `app_hermes_samwise` group; the dashboard retains its own native OAuth login. The `/outpost.goauthentik.io/` callback goes to Authentik behind the LAN allowlist, without recursive forward auth. The catch-all browser route authenticates the `/websockify` handshake too. Logging out or removing membership does not disconnect an already-open WebSocket; close the desktop session when finished.

The blueprint assigns this provider to Authentik's embedded outpost. Its `providers` field is the complete membership list, not an append operation. Put future embedded-outpost providers in the same canonical list or this blueprint will detach them. The outpost must already have its public `authentik_host` configured; the blueprint preserves that existing configuration.

Managed persistence gives each Hermes profile a stable browser identity. Cookies and localStorage live on `hermes-browser-samwise`, separate from Hermes files; IndexedDB is not enabled. Conversations using the same profile share its logged-in browser state. No automatic logout is performed at session end. The Node server runs directly as PID 1 so SIGTERM saves state before the browser exits; the Pod allows 60 seconds for shutdown, shared with the gateway and other sidecars. Forced termination or a node failure can lose changes since the last save. NFS administrators can read stored sessions; treat this PVC as credential-bearing data. Crash-report telemetry is disabled.

Requested browsing can reach both public sites and homelab services. Page text is untrusted input. Purchases, payments, account/permission changes, destructive actions and sharing private data require confirmation. These are instructions to the agent, not technical permission controls. Use the protected desktop for manual sign-in rather than sending passwords in chat: typed fields, including passwords, can appear in model snapshots. Pages can attempt requests to LAN destinations, so allowing homelab browsing also permits that exposure.

A credential-free staging Pod verified plugin installation, managed identity, public navigation/snapshots, the noVNC WebSocket handshake, rejection of control-API requests to the Pod IP, and cookie/localStorage retention after both a sidecar restart and Pod replacement. The rendered blueprint passed Authentik's live importer validation inside its rollback transaction. The staging Pod and PVC were removed. These checks did not test owner/nonmember SSO or external LAN filtering through the new hostname.

Before rollout:

1. Merge through owner review, then wait for both `authentik` and `ai` to sync. Check that the blueprint applied, its proxy provider is attached to the embedded outpost, and the browser PVC is bound.
2. Review the existing `/opt/data/SOUL.md` and add the **Browser** section from `instances/samwise/SOUL.md` without discarding personal edits. Updating the seed alone does not change an existing instance.
3. Run `hermes camofox status` in the gateway. It must report a reachable server and managed persistence. Ask for a public page and confirm browser tool calls in Telegram and the dashboard.
4. Test the desktop and `/websockify`: unauthenticated LAN clients must redirect to Authentik, a group member must connect, a nonmember must be denied, and a non-LAN request must be rejected. Local manifest tests do not establish these live authorization results.
5. Sign in through the desktop. Use a normal rollout restart to check that the login survives before relying on persistence. Do not test persistence with purchases, cart changes or home-device writes.

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

- [Hermes Camofox plugin](https://hermes-agent.nousresearch.com/docs/plugins/camofox)
- [Pinned Camofox plugin source](https://github.com/NousResearch/hermes-official-plugins/tree/1138f25c8b7b5a8fb882b3161e248f29abbd1a46/camofox)
- [Camofox server](https://github.com/jo-inc/camofox-browser)
- [Authentik Traefik forward auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_traefik/)
- [Authentik embedded outpost](https://docs.goauthentik.io/add-secure-apps/outposts/embedded/)
- [Better Mealie MCP v3.30.0 setup](https://github.com/djwmarcx/better-mealie-mcp/tree/v3.30.0)
- [Better Mealie MCP v3.30.0 server configuration](https://github.com/djwmarcx/better-mealie-mcp/blob/v3.30.0/better_mealie_mcp/server.py)
- [Mealie API tokens](https://docs.mealie.io/documentation/getting-started/api-usage/)
- [Kubernetes native sidecar startup and lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/)

- [Hermes v0.22.6 profiles and isolation limits](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/website/docs/user-guide/profiles.md)
- [Hermes v0.22.6 dashboard](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/website/docs/user-guide/features/web-dashboard.md)
- [Hermes v0.22.6 plugin installation](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/hermes_cli/plugins_cmd_install.py)
- [Pinned official Home Assistant plugin](https://github.com/NousResearch/hermes-official-plugins/tree/4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072/homeassistant)
- [Authentik blueprint structure](https://docs.goauthentik.io/customize/blueprints/v1/structure/)
- [Telegram Bot API profile methods](https://core.telegram.org/bots/api#setmyname)
