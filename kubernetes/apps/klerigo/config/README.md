# klerigo secrets

Encrypted with SOPS and committed here, but **not** listed in
`kustomization.yaml`, so ArgoCD never manages them. Apply them by hand:

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
