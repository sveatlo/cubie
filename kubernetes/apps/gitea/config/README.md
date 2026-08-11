# gitea secrets

Encrypted with SOPS and committed here, but **not** listed in
`kustomization.yaml`, so ArgoCD never manages them. Apply them by hand once the
namespace exists:

```sh
hack/apply-secret.sh kubernetes/apps/gitea/config/gitea-admin.yaml.sops
hack/apply-secret.sh kubernetes/apps/gitea/config/gitea-oidc.yaml.sops
```

Postgres is not here: CNPG generates `gitea-db-app` from
`config/cnpg-cluster.yaml`, and `values.yaml` reads the password out of it.

## gitea-admin.yaml.sops

`username` and `password` for the local admin account, created by the chart's
init container. `passwordMode: keepUpdated` means the secret wins: rotate it,
resync, and the account password follows.

This account exists for the admin panel — runner registration tokens, package
cleanup — because those pages are reachable without going through Authentik.

## gitea-oidc.yaml.sops

One generated credential pair, written into two namespaces because both ends of
the handshake need it: `gitea-oidc` in `authentik` (read as env by
`kubernetes/apps/authentik/config/blueprint-gitea.yaml`, which declares the
provider) and `gitea-oauth` in `gitea` (the client). They are in one file so
the two copies cannot drift — a mismatch surfaces as a failed login, not as a
config error.

Nothing is clicked together in the Authentik UI: the provider, its redirect URI
and the application (slug `gitea`, which the discovery URL is built from) all
live in that blueprint.

To rotate, edit both halves to the same new values and reapply:

```sh
hack/edit-secret.sh kubernetes/apps/gitea/config/gitea-oidc.yaml.sops
hack/apply-secret.sh kubernetes/apps/gitea/config/gitea-oidc.yaml.sops
kubectl -n authentik rollout restart deploy/authentik-server deploy/authentik-worker
kubectl -n gitea rollout restart deploy/gitea
```

Accounts are created on first sign-in (`ENABLE_AUTO_REGISTRATION`), and the
Gitea username comes from the `nickname` claim. Registration through the web
form is off; Authentik is the only way in apart from the admin account above.
