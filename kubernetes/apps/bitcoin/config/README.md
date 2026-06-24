# bitcoin namespace — Bitcoin Core + LND + ThunderHub

Pruned mainnet `bitcoind` → `lnd` → `thunderhub` UI. All in the `bitcoin`
namespace, auto-discovered by the root ApplicationSet.

## Components

| Workload   | Kind        | Storage          | Exposed                          |
|------------|-------------|------------------|----------------------------------|
| bitcoind   | StatefulSet | 30Gi nfs (RWO)   | in-cluster: rpc/zmq/p2p          |
| lnd        | StatefulSet | 5Gi nfs (RWX)    | in-cluster: grpc/rest/p2p        |
| thunderhub | Deployment  | reads lnd PVC ro | `thunderhub.${DOMAIN_0}` (LAN) |

`prune=10000` keeps chain data ~10GB. LND runs against the pruned backend and
back-fills historical blocks from the P2P network.

## Secrets (manual, one-time — not in kustomization.yaml)

Three SOPS secrets must be filled, encrypted, and applied by hand.

### 1. Generate the bitcoind RPC credential
```bash
curl -sSL https://raw.githubusercontent.com/bitcoin/bitcoin/master/share/rpcauth/rpcauth.py \
  | python3 - lnd
```
Prints an `rpcauth=lnd:<salt>$<hash>` line **and** a plaintext password.

- Put the `rpcauth=...` value into `bitcoind-secret.yaml` (`REPLACE_ME_RPCAUTH`).
- Put the plaintext password into `lnd-secret.yaml` (`REPLACE_ME_RPC_PASSWORD`).

### 2. Pick a wallet password + UI password
- `lnd-secret.yaml`: `REPLACE_ME_WALLET_PASSWORD` (chosen in step 4 below).
- `thunderhub-secret.yaml`: `REPLACE_ME_UI_PASSWORD` (ThunderHub login).

### 3. Encrypt + apply
```bash
for s in bitcoind lnd thunderhub; do
  hack/edit-secret.sh kubernetes/apps/bitcoin/config/${s}-secret.yaml   # -> .sops
done
kubectl create namespace bitcoin --dry-run=client -o yaml | kubectl apply -f -
for s in bitcoind lnd thunderhub; do
  hack/decrypt-secret.sh kubernetes/apps/bitcoin/config/${s}-secret.yaml.sops | kubectl apply -f -
done
```

### 4. First-run: create the LND wallet
On first boot LND finds no wallet and waits in its RPC-unlocker state (it does
**not** auto-create — that would generate an unseen seed). Create the wallet
explicitly to capture the seed:
```bash
kubectl -n bitcoin exec -it lnd-0 -- lncli create
```
Use the **same** password as `REPLACE_ME_WALLET_PASSWORD`. **Write down the 24-word
seed.** After this, LND auto-unlocks on every restart via the password file.

## Notes
- IBD on NFS is slow; `lnd` will crashloop-retry until `bitcoind` is synced
  enough to answer RPC. Expected on first deploy.
- `bitcoind` RPC is reachable only inside the cluster (`rpcallowip=10.0.0.0/8`).
- ThunderHub mounts `data-lnd-0` read-only — depends on the StatefulSet PVC name.
