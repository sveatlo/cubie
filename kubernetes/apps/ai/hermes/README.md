# Hermes household instances

Samwise is the first household instance. The shared `base/` supplies the pinned Hermes runtime, Camofox sidecar, dashboard/browser/API Services, separate runtime/browser PVCs and initialization. Each directory under `instances/` supplies identity, configuration, hostname, resource-name patches, selectors and Secret references.

| Setting | Samwise |
| --- | --- |
| Deployment / PVC | `ai/hermes-samwise` |
| Dashboard | `https://samwise.${DOMAIN_0}` |
| Browser desktop | `https://samwise-browser.${DOMAIN_0}/vnc.html?autoconnect=true&resize=remote` |
| Browser PVC | `ai/hermes-samwise-browser` |
| Assist API | `https://samwise-api.${DOMAIN_0}`, bearer authentication and LAN allowlist |
| Authentik application | `Samwise (Hermes)`, slug `hermes-samwise` |
| Dashboard OAuth client | `hermes-samwise-dashboard`, public client with PKCE |
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
hack/apply-secret.sh kubernetes/apps/ai/config/hermes-samwise-credentials.yaml.sops
hack/apply-secret.sh kubernetes/apps/ai/config/hermes-samwise-homeassistant.yaml.sops
hack/apply-secret.sh kubernetes/apps/ai/config/hermes-samwise-api.yaml.sops
```

The first Secret contains only the existing four Telegram settings. The second contains only the existing `HASS_URL` and `HASS_TOKEN`. The third contains the dedicated inbound `API_SERVER_KEY`; it is separate from the agent's HA administrator credential and Telegram settings. No operator, GitHub or webhook credentials are copied. Do not restore the old `.env`.

The configure init container projects all three Secrets into `/managed-env` and synchronizes their keys into `/opt/data/.env` before invoking Hermes. The gateway can read the same projection; browser and Mealie containers cannot. The profile file is mode `0600`, preserves unrelated runtime settings, and records managed key names (not values) in `.managed-env-keys.json`. A later rollout refreshes rotated values and removes keys deleted from the managed Secrets. Secret updates still require a Pod rollout; changing projected files alone does not rerun initialization.

This profile copy is required by Hermes v0.22.7: `hermes_cli.config.reload_env()` removes known environment variables absent from `.env`, including Kubernetes-injected Telegram and Home Assistant settings. An owner-issued `/reload` reproduced the failure on 2026-11-04: ID `221832708` was authorized initially, then denied after its process allowlist was removed. A gateway-only restart restored the injected environment; syncing the managed keys into the profile prevents the next reload from deleting them. SOPS-encrypted Secrets remain the source of truth; do not rotate these managed values through the dashboard.

OpenAI and Rohlík require fresh sign-ins. No OAuth files or other state are copied from the old PVC. Stop the old gateway before starting Samwise so two instances do not poll the same Telegram bot.

## Home Assistant Assist API

The gateway serves the existing Hermes API on `0.0.0.0:8642`. The instance-specific ClusterIP Service and `samwise-api.${DOMAIN_0}` ingress expose it over HTTPS with `traefik-lan-only`; requests still need the dedicated bearer key. Interactive Authentik is deliberately absent so HA can authenticate noninteractively. The LAN middleware is an ingress restriction, not a pod-level NetworkPolicy. Samwise's tools, memory, identity and approval policy are unchanged.

The dedicated Secret was applied on 2026-11-06. Provision it before deploying changes that reference it. It must be both injected into the gateway environment and included in `/managed-env` so initialization synchronizes `API_SERVER_KEY` into the profile `.env`. Hermes's scoped secret resolver prefers a stored profile value over the process environment: leaving an old profile key in place makes the new injected key receive HTTP 401 while the old key still authenticates. Secret rotation therefore requires the managed-profile sync and a Pod rollout. Deploy through owner merge and Argo reconciliation; do not directly patch the deployment to bypass self-healing.

After sync:

```bash
kubectl -n ai exec deployment/hermes-samwise -c gateway -- \
  /opt/hermes/.venv/bin/python /config/smoke_test.py api
```

This checks authenticated capabilities and unauthenticated rejection without inference. Verify trusted HTTPS and authenticated reachability from HA separately. A read-only `/v1/runs` marker request on the existing loopback API completed successfully in 3.60 seconds; this does not prove the new ingress works.

Use the unmodified [WolframRavenwolf Hermes Conversation integration](https://github.com/WolframRavenwolf/hermes-ha-integration), checked out at `home-automation/hass/hermes-assist` in the surrounding Mirkwood workspace. The owner dropped the custom adapter fork on 2026-11-06. Follow upstream installation and configuration; custom durable Runs, deferred delivery and native approval-control additions are not part of this setup. Keep the old Assist pipeline until text, phone and physical-room checks pass. No HA integration or pipeline was changed during API preparation.

## Mealie

Samwise uses `djwmarcx/better-mealie-mcp:3.30.0`, pinned by image digest to match Mealie v3.30.0. Renovate's Kubernetes manager tracks this image and its digest. A package-specific versioning rule also treats upstream `-r2`, `-r3`, etc. revisions as stable build updates rather than separate compatibility channels. All 283 tools are exposed, including administrative endpoints. Actual permissions come from the API token's account; this instance deliberately uses a separately named token from the owner's existing account. Revoking that token does not require changing the owner's password.

The MCP runs as a Kubernetes native sidecar in Samwise's Pod. Its startup probe must pass before the gateway starts. It listens on `127.0.0.1:8000/mcp`, with no Service or ingress, and calls `http://mealie.mealie.svc.cluster.local:9000`. It receives no Hermes PVC or configuration mount. Only this sidecar receives `MEALIE_API_TOKEN`, from the dedicated `ai/hermes-samwise-mealie` Secret; the gateway accesses Mealie through MCP rather than receiving its token directly. The sidecar has a read-only root filesystem and a small temporary volume.

Mealie tools are available to Telegram, CLI and dashboard/API sessions. Hermes's default tool-search behavior defers MCP schemas until needed. The full tool inventory remains available; long names are shortened by Hermes to fit provider limits. Listing tools alone does not prove the API token works.

Before merging the integration or rotating its token:

1. Create a separately named token under Mealie's Profile → Manage API Tokens (`/user/profile/api-tokens`). The account must have the permissions Samwise needs; this token has no independent API scopes.
2. Store it in the SOPS-encrypted `kubernetes/apps/ai/config/hermes-samwise-mealie.yaml.sops`, Secret `ai/hermes-samwise-mealie`, key `MEALIE_API_TOKEN`. Use `hack/edit-secret.sh`; never commit plaintext or add it to the Telegram/Home Assistant Secrets.
3. Apply it before the owner merges the integration:

   ```bash
   hack/apply-secret.sh kubernetes/apps/ai/config/hermes-samwise-mealie.yaml.sops
   ```

The initial dedicated Secret was applied on 2026-11-04, and a read-only `/api/users/self` request verified its authentication and administrative/food-organization permissions. The integration still requires an owner merge and post-sync MCP discovery/read verification. A missing Secret or failed sidecar startup blocks Samwise's rollout; do not merge before provisioning it. A separate instance needs its own token and Secret reference.

## Camofox browsing

Camofox `1.18.1` is pinned by image digest and starts as a native sidecar before Hermes initialization. Renovate's existing anchored-image regex manager in `renovate.json` tracks both its version and digest. Plugin commit pins are separate and currently updated manually in `base/init.py`: changing `PLUGIN_REFS` changes the generated ConfigMap hash, which rolls the Pod and reinstalls the affected plugin. The upstream image stores its browser under root-only `/root`, so a capability-free root init container copies the bundle into an ephemeral volume. The browser then runs as UID/GID `10000`, with a read-only root filesystem and bundle. It receives neither the Hermes PVC nor its Secrets. Its REST API (`9377`) and native VNC (`5900`) bind to loopback; only noVNC (`6080`) has a ClusterIP Service. Loopback is a Pod boundary, not a gateway credential boundary: any container in this Pod can control the browser. Other cluster workloads and cluster administrators can reach the internal noVNC Service; there is no hostile-workload isolation or VNC password.

The external noVNC ingress requires both the LAN allowlist and Authentik forward auth. It has a separate `hermes-samwise-browser` application bound to the existing `app_hermes_samwise` group; the dashboard retains its own native OAuth login. The `/outpost.goauthentik.io/` callback goes to Authentik behind the LAN allowlist, without recursive forward auth. The catch-all browser route authenticates the `/websockify` handshake too. Logging out or removing membership does not disconnect an already-open WebSocket; close the desktop session when finished.

The blueprint assigns this provider to Authentik's embedded outpost. Its `providers` field is the complete membership list, not an append operation. Put future embedded-outpost providers in the same canonical list or this blueprint will detach them. The outpost must already have its public `authentik_host` configured; the blueprint preserves that existing configuration.

Managed persistence gives each Hermes profile a stable browser identity. Cookies and localStorage live on `hermes-samwise-browser`, separate from Hermes files; IndexedDB is not enabled. Conversations using the same profile share its logged-in browser state. No automatic logout is performed at session end. The Node server runs directly as PID 1 so SIGTERM saves state before the browser exits; the Pod allows 60 seconds for shutdown, shared with the gateway and other sidecars. Forced termination or a node failure can lose changes since the last save. NFS administrators can read stored sessions; treat this PVC as credential-bearing data. Crash-report telemetry is disabled.

Requested browsing can reach both public sites and homelab services. Page text is untrusted input. Purchases, payments, account/permission changes, destructive actions and sharing private data require confirmation. These are instructions to the agent, not technical permission controls. Use the protected desktop for manual sign-in rather than sending passwords in chat: typed fields, including passwords, can appear in model snapshots. Pages can attempt requests to LAN destinations, so allowing homelab browsing also permits that exposure.

A credential-free staging Pod verified plugin installation, managed identity, public navigation/snapshots, the noVNC WebSocket handshake, rejection of control-API requests to the Pod IP, and cookie/localStorage retention after both a sidecar restart and Pod replacement. The rendered blueprint passed Authentik's live importer validation inside its rollback transaction. The staging Pod and PVC were removed. These checks did not test owner/nonmember SSO or external LAN filtering through the new hostname.

Before rollout:

1. Merge through owner review, then wait for both `authentik` and `ai` to sync. Check that the blueprint applied, its proxy provider is attached to the embedded outpost, and the browser PVC is bound.
2. Review the existing `/opt/data/SOUL.md` and add the **Browser** section from `instances/samwise/SOUL.md` without discarding personal edits. Updating the seed alone does not change an existing instance.
3. Run `hermes camofox status` in the gateway. It must report a reachable server and managed persistence. Ask for a public page and confirm browser tool calls in Telegram and the dashboard.
4. Test the desktop and `/websockify`: unauthenticated LAN clients must redirect to Authentik, a group member must connect, a nonmember must be denied, and a non-LAN request must be rejected. Local manifest tests do not establish these live authorization results.
5. Sign in through the desktop. Use a normal rollout restart to check that the login survives before relying on persistence. Do not test persistence with purchases, cart changes or home-device writes.

## Internal identifier cutover

Resources use `hermes-samwise` followed by the component (`-dashboard`, `-browser`, `-browser-auth`, `-config`, `-credentials`, `-homeassistant`, `-mealie`, `-api`). The ConfigMap also carries Kustomize's content hash. The instance label is `hermes-samwise`; the reusable base keeps generic names. Name-change patches record the original resource identities so Kustomize updates built-in references, including the generated ConfigMap. Traefik CRD references are explicit.

Public URLs (`samwise` and `samwise-browser`) and the Authentik group `app_hermes_samwise` are unchanged. The dashboard OAuth client becomes `hermes-samwise-dashboard`; its provider and issuer remain `hermes-samwise`. Authentik and Hermes must both sync before testing sign-in; existing dashboard sessions may need a new login.

Staged on 2026-11-04:

- The three renamed Secrets were created from verified identical encrypted/live data. Original Secrets remain available to the running Pod; no credentials were rotated.
- Runtime PVC `ai/hermes-samwise` remains on PV `pvc-742cbb28-09bb-471e-8baa-5379b2f1d36e`; it was not copied or rebound.
- Browser PVC `ai/hermes-samwise-browser` is bound to new PV `pvc-10201fb6-e7c6-4e1c-8dbc-49b3226d6024`. No deployed browser PVC existed, so there was no browser state to move.
- The production Deployment and Pod were not changed.

**Owner maintenance is required when merging this rename.** The existing Deployment selector contains `app.kubernetes.io/instance: samwise`. Kubernetes rejects changing it in place, even with the `Recreate` strategy. An ordinary sync will report an immutable-selector error; do not add a permanent force-replace annotation, which would recreate the Deployment on every sync.

1. Merge only during an agreed maintenance window. The renamed Services select the new instance label, so a partial sync can interrupt dashboard traffic before the gateway is replaced.
2. Once Argo CD shows the merged revision as its desired state, delete only the Deployment with `kubectl -n ai delete deployment hermes-samwise --cascade=foreground --wait=true`. Foreground deletion keeps its name occupied until the old Pods are gone. Then sync `ai` again (or let automated reconciliation recreate it). Do not delete the PVC, use orphan/background deletion, or run old and new gateways together against its state.
3. Wait for the new Deployment and both `ai` and `authentik` applications to become healthy. Verify selector and Pod label `hermes-samwise`, the unchanged runtime PVC binding, all three renamed Secret references and dashboard sign-in with the renamed OAuth client. Then perform the browser checks above.
4. Retain the old Secrets until rollback is no longer needed. Delete only `ai/hermes-credentials-samwise`, `ai/hermes-homeassistant-samwise` and `ai/hermes-mealie-samwise`, after checking that no Pod references them. Rolling back this PR also requires replacing the Deployment because the selector changes back; it does not require moving the runtime PVC.

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

Delete the old live Secrets `ai/hermes-credentials`, `ai/hermes-homeassistant`, `ai/hermes-ssh`, `ai/hermes-talos` and `monitoring/hermes-alert-webhook` after confirming no remaining consumers. The HA token itself stays valid in `hermes-samwise-homeassistant`. Remove obsolete local setup helpers and any credential copies discovered during cutover; do not print their contents.

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

Copy `instances/samwise/` to a new instance directory. Start its replica count at zero. Change the resource-name patches, instance label, explicit Traefik references, Secret references, hostname, OAuth issuer/client and identity; add the directory to the parent Kustomization. Create a separate Authentik group, application, provider and strict callback, and new encrypted Secrets. Use a different Telegram bot unless an explicit routing design replaces polling. Start with a fresh PVC and authorize that instance independently: do not clone Samwise's state or share rotating OAuth token files.

All instances start at zero replicas unless their overlay explicitly activates them. Never add a second instance without reviewing both rendered selectors and credential routing.

## References

- [Hermes Telegram settings and profile `.env`](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram)
- [python-dotenv file updates](https://bbc2.github.io/python-dotenv/reference/)

- [Kustomize resource-name changes](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/patches/)
- [Kubernetes immutable Deployment selectors](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#label-selector-updates)
- [Kubernetes foreground cascading deletion](https://kubernetes.io/docs/concepts/workloads/controllers/garbage-collection/#foreground-deletion)
- [Hermes Camofox plugin](https://hermes-agent.nousresearch.com/docs/plugins/camofox)
- [Pinned Camofox plugin source](https://github.com/NousResearch/hermes-official-plugins/tree/1138f25c8b7b5a8fb882b3161e248f29abbd1a46/camofox)
- [Camofox server](https://github.com/jo-inc/camofox-browser)
- [Authentik Traefik forward auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_traefik/)
- [Authentik embedded outpost](https://docs.goauthentik.io/add-secure-apps/outposts/embedded/)
- [Better Mealie MCP v3.30.0 setup](https://github.com/djwmarcx/better-mealie-mcp/tree/v3.30.0)
- [Better Mealie MCP v3.30.0 server configuration](https://github.com/djwmarcx/better-mealie-mcp/blob/v3.30.0/better_mealie_mcp/server.py)
- [Mealie API tokens](https://docs.mealie.io/documentation/getting-started/api-usage/)
- [Kubernetes native sidecar startup and lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/)

- [Hermes v0.22.7 API server](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/website/docs/user-guide/api-server.md)
- [Hermes v0.22.6 profiles and isolation limits](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/website/docs/user-guide/profiles.md)
- [Hermes v0.22.6 dashboard](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/website/docs/user-guide/features/web-dashboard.md)
- [Hermes v0.22.6 plugin installation](https://github.com/NousResearch/hermes-agent/blob/v0.22.6/hermes_cli/plugins_cmd_install.py)
- [Pinned official Home Assistant plugin](https://github.com/NousResearch/hermes-official-plugins/tree/4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072/homeassistant)
- [Authentik blueprint structure](https://docs.goauthentik.io/customize/blueprints/v1/structure/)
- [Telegram Bot API profile methods](https://core.telegram.org/bots/api#setmyname)
