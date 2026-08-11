# gitea secrets

Encrypted with SOPS and committed here, but **not** listed in
`kustomization.yaml`, so ArgoCD never manages them. Apply them by hand once the
namespace exists:

```sh
hack/apply-secret.sh kubernetes/apps/gitea/config/gitea-admin.yaml.sops
hack/apply-secret.sh kubernetes/apps/gitea/config/gitea-oauth.yaml.sops
```

Postgres is not here: CNPG generates `gitea-db-app` from
`config/cnpg-cluster.yaml`, and `values.yaml` reads the password out of it.

## gitea-admin.yaml.sops

`username` and `password` for the local admin account, created by the chart's
init container. `passwordMode: keepUpdated` means the secret wins: rotate it,
resync, and the account password follows.

This account exists for the admin panel — runner registration tokens, package
cleanup — because those pages are reachable without going through Authentik.

## gitea-oauth.yaml.sops

**Ships with `REPLACE_ME`.** Create the provider in Authentik first, then fill
in `key` (client ID) and `secret` (client secret):

```sh
hack/edit-secret.sh kubernetes/apps/gitea/config/gitea-oauth.yaml.sops
```

In Authentik: an OAuth2/OpenID provider with redirect URI
`https://git.<DOMAIN_4>/user/oauth2/authentik/callback`, signing key set, bound
to an application whose **slug is `gitea`** — `values.yaml` builds the discovery
URL from that slug, so a different one silently breaks sign-in.

Accounts are created on first sign-in (`ENABLE_AUTO_REGISTRATION`), and the
Gitea username comes from the `nickname` claim. Registration through the web
form is off; Authentik is the only way in apart from the admin account above.
