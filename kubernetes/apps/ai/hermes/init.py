import hashlib
from pathlib import Path
import shutil
from urllib.request import urlopen

home = Path("/opt/data")
for directory in ("workspace", "tools", "alerts"):
    (home / directory).mkdir(parents=True, exist_ok=True)
for name in ("config.yaml", "SOUL.md"):
    shutil.copyfile(Path("/config") / name, home / name)
(home / ".gitconfig").write_text(
    '[credential "https://github.com"]\n'
    '    helper = !/opt/hermes/.venv/bin/python /config/git-credential.py\n'
    '    username = x-access-token\n'
)
ssh = home / ".ssh"
ssh.mkdir(mode=0o700, exist_ok=True)
ssh.chmod(0o700)
for source, name in (("/ssh/id_ed25519", "id_ed25519"),
                     ("/config/id_ed25519.pub", "id_ed25519.pub"),
                     ("/config/ssh-config", "config"),
                     ("/config/known_hosts", "known_hosts")):
    shutil.copyfile(source, ssh / name)
    (ssh / name).chmod(0o600)
for name, url, digest in (
    ("kubectl", "https://dl.k8s.io/release/v1.35.2/bin/linux/amd64/kubectl",
     "924eb50779153f20cb668117d141440b95df2f325a64452d78dff9469145e277"),
    ("talosctl", "https://github.com/siderolabs/talos/releases/download/v1.12.6/talosctl-linux-amd64",
     "4c41a3b10b075292e64b182283d558e9d8e935f43239de1ed4e4b14359593efb"),
):
    target = home / "tools" / name
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        with urlopen(url, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit(f"Checksum mismatch: {name}")
        target.write_bytes(data)
    target.chmod(0o755)
