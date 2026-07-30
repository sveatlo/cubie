# klerigo secrets

Encrypted with SOPS and committed here, but **not** listed in
`kustomization.yaml`, so ArgoCD never manages them. Apply them by hand:

## ghcr credentials (two, in different namespaces)

The chart and images are private, and they are fetched by two different things
that authenticate separately. Both need a **classic** PAT with `read:packages`;
fine-grained tokens cannot read GitHub Packages.

The repo-server renders the chart, so it needs the credential in `argocd`:

```sh
kubectl -n argocd create secret generic ghcr-registry-config \
  --from-file=config.json=<(printf '{"auths":{"ghcr.io":{"auth":"%s"}}}' \
    "$(printf '%s:%s' "$GH_USER" "$GH_TOKEN" | base64 -w0)")
kubectl -n argocd rollout restart deploy/argocd-repo-server
```

The kubelet pulls the images, so it needs its own in `klerigo`:

```sh
kubectl -n klerigo create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io --docker-username="$GH_USER" --docker-password="$GH_TOKEN"
```

Neither is committed here: the token is personal and rotates on its own
schedule. The repo-server mount is `optional`, so a missing one degrades to
private-chart apps failing to render rather than every app going down.

## The rest

```sh
hack/apply-secret.sh kubernetes/apps/klerigo/config/klerigo-db.yaml.sops
hack/apply-secret.sh kubernetes/apps/klerigo/config/klerigo-app.yaml.sops
hack/apply-secret.sh kubernetes/apps/klerigo/config/klerigo-smtp.yaml.sops
```

The namespace must exist first (`kubectl create namespace klerigo`), or ArgoCD
must have created it.

Edit any of them with `hack/edit-secret.sh <file>`.

## klerigo-db.yaml.sops

Five `kubernetes.io/basic-auth` secrets, one per service database. CNPG needs
`username` and `password` to create the managed role; the service reads
`database-url`, because CNPG generates a connection URI only for
`bootstrap.initdb` owners, never for managed roles.

The password therefore appears twice, and the two copies must agree. Nothing
validates that they do, and a mismatch surfaces as an auth failure at pod
startup rather than as a config error. If you rotate one by hand, rotate both.

## klerigo-app.yaml.sops

`klerigo-jwt` is shared by the gateway and identity: identity signs, the gateway
verifies, so a mismatch fails every login.

`klerigo-livekit` splits one key pair across three values because the LiveKit
server and `services/calls` read different shapes. `keys` is
`<api-key>: <api-secret>`, and `deps-values.yaml` names that same api-key under
`webhook.api_key` so LiveKit signs webhooks with a key it actually holds.

`klerigo-storage` is the source of truth for the Garage credentials: the init
Job imports these rather than generating its own, so `courses` signs URLs with
a key that exists. `klerigo-garage` holds Garage's own RPC secret and admin
token, kept out of the ConfigMap that carries the rest of its config.

## klerigo-smtp.yaml.sops

**Ships with `REPLACE_ME` placeholders.** Fill in a real provider before
expecting mail to work:

```sh
hack/edit-secret.sh kubernetes/apps/klerigo/config/klerigo-smtp.yaml.sops
```

`port` is consumed as a string. `username` and `password` must both be present:
together they switch the mailer to authenticated STARTTLS, and notifications
refuses to start with only one of them rather than quietly sending
unauthenticated.
