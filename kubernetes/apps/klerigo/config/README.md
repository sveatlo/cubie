# klerigo secrets

These are applied by hand and deliberately kept out of git, so ArgoCD never
manages them. Nothing here is created by a sync; a fresh cluster needs all of
them present before the pods will start. This file is the only record that they
exist.

Create them in the `klerigo` namespace.

## Database credentials (five)

CNPG requires `kubernetes.io/basic-auth` with both `username` and `password`.
The `database-url` key is extra, and is what the service itself reads: CNPG
generates no connection URI for managed roles, only for `bootstrap.initdb`
owners. The password inside the URL and the `password` key must agree. Nothing
validates that they do, and a mismatch surfaces as an auth failure at pod
startup rather than as a config error.

```sh
for db in identity courses vocabulary notifications calls; do
  pw=$(openssl rand -hex 24)
  kubectl -n klerigo create secret generic "klerigo-db-$db" \
    --type=kubernetes.io/basic-auth \
    --from-literal=username="$db" \
    --from-literal=password="$pw" \
    --from-literal=database-url="postgres://$db:$pw@klerigo-db-rw:5432/$db"
done
```

## Application secrets

`JWT_SECRET` is shared by the gateway and identity: the gateway verifies what
identity signs, so the two must match exactly.

```sh
kubectl -n klerigo create secret generic klerigo-jwt \
  --from-literal=jwt-secret="$(openssl rand -hex 32)"
```

LiveKit reads `keys` as `<api-key>: <secret>`, while calls takes the two halves
separately. All three values have to describe the same pair.

```sh
LK_KEY=klerigo
LK_SECRET=$(openssl rand -hex 32)
kubectl -n klerigo create secret generic klerigo-livekit \
  --from-literal=api-key="$LK_KEY" \
  --from-literal=api-secret="$LK_SECRET" \
  --from-literal=keys="$LK_KEY: $LK_SECRET"
```

The storage key is imported into Garage by the init Job rather than generated
by it, so these values are the source of truth. The access key id must be 26
characters starting with `GK`.

```sh
kubectl -n klerigo create secret generic klerigo-storage \
  --from-literal=access-key-id="GK$(openssl rand -hex 12)" \
  --from-literal=secret-access-key="$(openssl rand -hex 32)"

kubectl -n klerigo create secret generic klerigo-garage \
  --from-literal=rpc-secret="$(openssl rand -hex 32)" \
  --from-literal=admin-token="$(openssl rand -hex 32)"
```

## SMTP

Configured against a real provider; there is no in-cluster mail sink. `port` is
consumed as a string. `username` and `password` must both be present: together
they switch the mailer to authenticated STARTTLS, and notifications refuses to
start with only one of them rather than quietly sending unauthenticated.

```sh
kubectl -n klerigo create secret generic klerigo-smtp \
  --from-literal=host=... \
  --from-literal=port=587 \
  --from-literal=username=... \
  --from-literal=password=... \
  --from-literal=from=no-reply@klerigo.com
```
