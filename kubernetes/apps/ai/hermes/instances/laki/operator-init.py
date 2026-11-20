import hashlib
import io
import os
from pathlib import Path
import tarfile
from urllib.request import urlopen


TOOLS = (
    ("kubectl", "https://dl.k8s.io/release/v1.35.2/bin/linux/amd64/kubectl",
     "924eb50779153f20cb668117d141440b95df2f325a64452d78dff9469145e277"),
    ("talosctl", "https://github.com/siderolabs/talos/releases/download/v1.12.6/talosctl-linux-amd64",
     "4c41a3b10b075292e64b182283d558e9d8e935f43239de1ed4e4b14359593efb"),
)


KRAKEN_URL = "https://github.com/krakenfx/kraken-cli/releases/download/v0.5.1/kraken-cli-x86_64-unknown-linux-gnu.tar.gz"
KRAKEN_ARCHIVE_SHA256 = "a5110521449d74d3d334acb42ffee3b5a7b50112ec845159c1f4a63335148263"
KRAKEN_BINARY_SHA256 = "0533351418f4efd67b534c143aa870f96eb16541dbb0768d6d8c5f1471dac6ae"
KRAKEN_MEMBER = "kraken-cli-x86_64-unknown-linux-gnu/kraken-mcp"


def install_kraken(directory, fetch=urlopen):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "kraken-mcp"
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == KRAKEN_BINARY_SHA256:
        target.chmod(0o755)
        return
    with fetch(KRAKEN_URL, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != KRAKEN_ARCHIVE_SHA256:
        raise RuntimeError("Checksum mismatch: Kraken archive")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = archive.getmember(KRAKEN_MEMBER)
        if not member.isfile():
            raise RuntimeError("Kraken MCP archive member is not a regular file")
        with archive.extractfile(member) as binary:
            data = binary.read()
    if hashlib.sha256(data).hexdigest() != KRAKEN_BINARY_SHA256:
        raise RuntimeError("Checksum mismatch: kraken-mcp")
    temporary = directory / ".kraken-mcp.download"
    temporary.write_bytes(data)
    temporary.chmod(0o755)
    temporary.replace(target)


def install_tools(directory, tools=TOOLS, fetch=urlopen):
    directory.mkdir(parents=True, exist_ok=True)
    for name, url, digest in tools:
        target = directory / name
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            with fetch(url, timeout=120) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"Checksum mismatch: {name}")
            temporary = directory / f".{name}.download"
            temporary.write_bytes(data)
            temporary.chmod(0o755)
            temporary.replace(target)
        target.chmod(0o755)


def initialize(home):
    install_tools(home / "tools")
    install_kraken(home / "tools")
    config = home / ".gitconfig"
    config.write_text(
        '[credential]\n'
        '    helper =\n'
        '[credential "https://github.com"]\n'
        '    helper = !/opt/hermes/.venv/bin/python /config/git-credential.py\n'
        '    username = x-access-token\n'
    )
    config.chmod(0o600)


if __name__ == "__main__":
    os.umask(0o077)
    initialize(Path(os.environ["HERMES_HOME"]))
