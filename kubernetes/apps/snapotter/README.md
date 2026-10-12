# SnapOtter

Public URL: https://tools.mirkwood.casa

SnapOtter uses native OIDC with Authentik. Only members of `app_snapotter` can sign in through SSO. New SSO accounts receive the `user` role. Group membership is managed in Authentik, not in the blueprint.

Local login remains available upstream. The initial `admin` password is generated randomly and stored in `config/snapotter-secret.yaml.sops`, key `admin-password`. Use it for administration and account-role changes. Local accounts bypass the Authentik group check; do not create local accounts for ordinary users.

## Deploy

Apply both encrypted secrets before ArgoCD syncs the applications:

```bash
hack/decrypt-secret.sh kubernetes/apps/snapotter/config/snapotter-secret.yaml.sops | kubectl apply -f -
hack/decrypt-secret.sh kubernetes/apps/authentik/config/snapotter-oidc.yaml.sops | kubectl apply -f -
```

The two secrets contain the same OIDC client secret. Rotate them together. The Authentik chart mounts `authentik-blueprint-snapotter` and supplies its `!Env` client secret to the blueprint importer.

ArgoCD discovers the `snapotter` directory after these changes reach the default branch. For an initial manual deployment, create the `snapotter` namespace, configure the Authentik provider first, then apply `hack/render.sh kubernetes/apps/snapotter` output. Avoid applying the entire Authentik render over an ArgoCD-managed installation.

## Storage and limits

- PostgreSQL 17 runs under the existing CloudNativePG operator with a 5 GiB NFS volume.
- `/data` uses a 20 GiB NFS PVC for files, settings, downloaded models and the pip cache.
- The Python environment uses a 15 GiB ephemeral volume at `/data/ai`; copying its many small files onto NFS made startup too slow. Models and the pip cache remain on NFS through nested mounts. Additional AI feature bundles must be reinstalled after pod replacement.
- Redis uses a 1 GiB NFS PVC with append-only persistence.
- Processing scratch uses a 10 GiB ephemeral volume. It is discarded when the pod is replaced.
- Two concurrent jobs, 1 GiB uploads, two CPU cores and 4 GiB memory limit the workload. AI models may need higher memory limits.
- App and Redis containers run as non-root with Linux capabilities dropped.

Analytics changes are deferred. The official image includes analytics; a runtime `SNAPOTTER_ANALYTICS=off` variable does not disable the baked-in implementation. Use the admin opt-out or build an image with that build argument when revisiting this.

## Verify

```bash
python3 hack/check-snapotter.py
```

The check verifies HTTPS health, rejection of unauthenticated sessions and registration, rejection of `admin/admin`, and the OIDC redirect to Authentik. It does not complete an interactive SSO login. Test group membership separately with an allowed and a denied Authentik account.

Removing a user from `app_snapotter` blocks future SSO authorizations, but does not immediately revoke an existing SnapOtter session. Revoke that user's SnapOtter sessions when removing access.

## Upstream references

- [Deployment](https://docs.snapotter.com/guide/deployment)
- [OIDC and Authentik configuration](https://docs.snapotter.com/guide/oidc)
- [Configuration](https://docs.snapotter.com/guide/configuration)
- [Pinned release v2.2.0](https://github.com/snapotter-hq/SnapOtter/releases/tag/v2.2.0)
