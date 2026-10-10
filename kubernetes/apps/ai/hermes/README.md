# Hermes on cubie

Hermes runs in namespace `ai` alongside Ollama and Open WebUI. The pinned image includes the SSH client and Chromium. The init container installs checksum-verified `kubectl` and cluster-version-matched `talosctl` on the dedicated PVC.

## Finish setup

Run the local credential wizard from the repository root:

```bash
bash tmp/hermes-setup.sh
```

The wizard is an ignored, one-off local file, not part of the repository. It needs Python with PyYAML, `kubectl`, `sops`, the age key, and the existing `talos/configs/talosconfig`. It requires Kubernetes context `admin@cubie`.

It walks through:

1. Telegram bot creation, disabled group invitations, and verified owner-only private chat.
2. GitHub repository token, Proxmox token, and trusted Proxmox CA when needed.
3. SOPS encryption, manual Secret application, and a temporary login pod. The gateway stays stopped.
4. OpenAI subscription device-code login and read-only integration checks. One small model request tests `gpt-6.1-sol`. Authentication, model eligibility, or quota failure stops setup without a paid fallback.
5. Gateway activation and a private Telegram greeting.

Secrets are not listed in Kustomize. The wizard provisions:

| Encrypted file | Secret | Namespace |
|---|---|---|
| `../config/hermes-credentials.yaml.sops` | `hermes-credentials` | `ai` |
| `../config/hermes-talos.yaml.sops` | `hermes-talos` | `ai` |
| `../config/hermes-ssh.yaml.sops` | `hermes-ssh` | `ai` |
| `../../../infrastructure/kube-prometheus-stack/config/hermes-alert-webhook.yaml.sops` | `hermes-alert-webhook` | `monitoring` |

The Talos Secret can also contain `proxmox-ca.crt`. TLS verification is enabled by default. The owner has explicitly selected `PROXMOX_VERIFY_TLS=false` for the configured Proxmox API: its HTTPS traffic is encrypted, but the server certificate and hostname are not verified. A network attacker could impersonate Proxmox and obtain the API token. Other integrations keep TLS verification enabled. Restore `PROXMOX_VERIFY_TLS=true` and provide a trusted CA to remove this exception.

To restore the existing credentials on a rebuilt cluster, apply all four encrypted Secrets from the repository root before reconciling the applications:

```bash
for secret in \
  kubernetes/apps/ai/config/hermes-credentials.yaml.sops \
  kubernetes/apps/ai/config/hermes-talos.yaml.sops \
  kubernetes/apps/ai/config/hermes-ssh.yaml.sops \
  kubernetes/infrastructure/kube-prometheus-stack/config/hermes-alert-webhook.yaml.sops; do
  hack/apply-secret.sh "$secret"
done
```

Restore the sensitive PVC backup separately. If its OAuth state is lost, the owner must repeat `hermes auth add openai-codex` inside a UID `10000` container, then rerun the integration/model gates before accepting alerts.

Only one Telegram gateway may poll this bot. Stop any old poller before rerunning Telegram verification. Do not leave a login pod running alongside the final Deployment.

Repository changes must land in the GitOps source for durable reconciliation. ArgoCD currently watches GitHub `HEAD`. Merge them yourself; the agent must not merge or push to `main` or `master`. Let ArgoCD reconcile the affected applications after merging. Applying monitoring changes manually can be undone by ArgoCD.

## LAN-only dashboard

Open `https://hermes.${DOMAIN_0}` from the LAN and sign in through Authentik as `sveatlo`. Traefik terminates HTTPS with the existing wildcard certificate and applies `traefik-lan-only@kubernetescrd`, which allows source addresses in `10.69.0.0/16`. The dashboard Service is ClusterIP-only on port `9119`; no public LoadBalancer or NodePort is added.

The official image's s6 supervisor runs the dashboard alongside the Telegram gateway as UID `10000`. Startup/readiness/liveness probes check its public `/api/status` endpoint. The dashboard shares the operator's PVC, credentials and permissions, so an authenticated dashboard session is an operator session, not a read-only monitoring view.

Authentik provisions a public OIDC client named `hermes-dashboard` through its Git-managed blueprint. Login uses authorization-code PKCE, an asymmetric signing key and the exact callback `https://hermes.${DOMAIN_0}/auth/callback`. The application's user binding admits only `sveatlo`; other SSO accounts are not granted access. No client secret or separate dashboard password is needed. Update the blueprint if the owner account is renamed.

`dashboard.public_url` fixes the callback URL and allowed browser origin. The dashboard trusts forwarded proxy metadata from the Flannel pod CIDR `10.244.0.0/16` so Traefik's changing pod IP can convey the HTTPS scheme and produce Secure cookies. That trusts other cluster pods' forwarding metadata too, not just Traefik. LAN filtering happens at the Ingress; in-cluster direct access still relies on the native login gate. Do not expose the dashboard Service outside the cluster or widen proxy trust to `*` or `/0`.

Dashboard edits to `SOUL.md` persist on the PVC. Dashboard edits to `config.yaml` remain subject to the Git-managed startup refresh. After reconciliation, verify the owner login, unauthenticated API rejection, Secure cookies, WebSocket access, and a denied non-LAN request. Neither an authenticated browser session nor a successful owner login is implied by a passing `/api/status` probe.

## Editable identity

Hermes loads `/opt/data/SOUL.md` from the writable PVC mounted at `/opt/data`. The repository's `SOUL.md` is only a first-boot seed: initialization copies it when the runtime file is missing and leaves an existing file untouched, including an empty file. Agent edits therefore survive container restarts and deployments. `config.yaml` remains Git-managed and is refreshed on startup.

Keep the directory mount rather than a single-file `subPath` mount so editors can replace the file atomically. Changes to the Git seed do not update an existing runtime identity. To reset it intentionally, back up the runtime file, remove it, and restart Hermes. Deleting the PVC without restoring its backup also loses the edited identity.

SOUL changes take effect in new Hermes sessions; an existing session keeps its frozen prompt.

## SSH targets

The public key is `id_ed25519.pub`. Its fingerprint is:

```text
SHA256:U8DAvaOY1vuGtAlSdHsg8w/9YTyvncDhyeXppDkS8b8
```

The private key is SOPS-encrypted in `../config/hermes-ssh.yaml.sops`. Initialization copies it to `/opt/data/.ssh/id_ed25519` with mode `0600`; the directory is `0700`.

For each non-Talos target:

1. Authorize the public key on a dedicated remote account with the permissions you intend Hermes to have.
2. Obtain its SSH host-key fingerprint through a trusted console or administrator. A network scan alone does not establish trust.
3. Compare the candidate host key against that fingerprint, then add the verified `known_hosts` entry to this directory's `known_hosts` file.
4. Reconcile the config to restart Hermes. Connect as `ssh account@hostname`.

Initialization replaces the runtime `known_hosts` file from this repository. Keep approved entries here, not only on the PVC. Unknown or changed host keys fail closed. Agent forwarding and interactive password prompts are disabled. Talos is API-only and must never receive SSH configuration.

## Browser

Chromium runs as UID `10001` in a separate container; operator processes use UID `10000`. The browser has an ephemeral profile, read-only root filesystem, dropped capabilities, and no operator environment, PVC, SSH key, Talos credentials, OpenAI credentials, or Kubernetes service-account token.

The Chrome DevTools endpoint listens on pod loopback `127.0.0.1:9222`. It is not exposed by a Service or Ingress. Hermes connects to it through `browser.cdp_url`. Private URLs are enabled for LAN dashboards. Browser cookies disappear when the browser container restarts.

Chromium uses `--no-sandbox` because its packaged launch cannot use a privileged Chromium sandbox here. Container and filesystem restrictions reduce credential exposure; they do not isolate network access from the rest of the pod. Use restricted dashboard accounts. Browser submission and mutation require owner approval under the operator instructions.

## Alert investigations

Alertmanager groups warning and critical alerts by `alertname` and `namespace`. Existing email delivery remains enabled. The authenticated webhook persists notifications before acknowledging them. A single worker processes investigations serially; interactive Telegram sessions can still run concurrently.

Investigations are diagnostic-only. They get terminal/file tools, a 25-turn limit, and a 600-second agent budget. Reports live under `/opt/data/alerts/results`; Telegram receives a report reference and diagnosis. The owner can refer to that incident in the private chat. Any remediation requires a new, specific approval.

The queue holds at most 100 groups; a full queue returns `503` so Alertmanager retries. Recent duplicate notifications are suppressed for four hours. Reports expire after seven days. Failed or interrupted model runs create `/opt/data/alerts/PAUSED`; queued incidents remain on disk.

After fixing the cause, explicitly approve resuming and remove the pause marker:

```bash
kubectl -n ai exec deployment/hermes -c alerts -- rm /opt/data/alerts/PAUSED
```

Delivery retries reuse the saved report rather than rerunning the model. Each acknowledged Telegram chunk is checkpointed so a later-chunk failure resumes at the saved offset. An ambiguous network response or crash before its checkpoint can still repeat a chunk; delivery is not exactly-once.

## Security and persistence

The operator has `cluster-admin` and the supplied Talos, GitHub, and Proxmox permissions. Ask-before-write and sanitized diagnostics are trust-based instructions, not a complete enforcement boundary. Native manual approvals catch only recognized dangerous commands. Broad credentials mean accidental or malicious operations remain possible.

The NFS PVC holds OAuth refresh tokens, the copied SSH key, the editable SOUL identity, conversations, memory, skills, workspaces, and incident reports. Git encryption does not encrypt that runtime data. Protect and back up the NAS accordingly. Never include raw credential files, Secret values, or environment dumps in model prompts, logs, or Telegram reports.

## Checks

The manifest regression tests require Python with PyYAML, already used by the setup wizard.

```bash
python -m unittest discover -s kubernetes/apps/ai/hermes -p 'test_*.py' -v
kubectl kustomize kubernetes/apps/ai/hermes
```

`smoke_test.py runtime` exercises installed tools, SSH permissions, and an actual Chromium navigation. `integrations` checks the configured services without mutations. `model` makes the single subscription-only request. Run these inside the login pod as the wizard does.

## References

- [Pinned Hermes image](https://github.com/NousResearch/hermes-agent/blob/v0.21.6/Dockerfile)
- [Hermes personality and SOUL](https://github.com/NousResearch/hermes-agent/blob/v0.21.6/website/docs/user-guide/features/personality.md)
- [Pinned Hermes dashboard guide](https://github.com/NousResearch/hermes-agent/blob/v0.21.6/website/docs/user-guide/features/web-dashboard.md)
- [Authentik OAuth2/OIDC provider](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/)
- [Authentik blueprints](https://docs.goauthentik.io/customize/blueprints/v1/structure/)
- [Hermes providers](https://hermes-agent.nousresearch.com/docs/integrations/providers/)
- [Hermes browser](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser/)
- [Proxmox API tokens](https://pve.proxmox.com/wiki/User_Management#_api_tokens)
- [GitHub token permissions](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
