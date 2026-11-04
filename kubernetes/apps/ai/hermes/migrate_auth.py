import json
from pathlib import Path
import shutil


FILES = (
    "auth.json",
    "mcp-tokens/rohlik-mcp.json",
    "mcp-tokens/rohlik-mcp.client.json",
    "mcp-tokens/rohlik-mcp.meta.json",
)


def migrate(source, target):
    if source.is_symlink() or target.is_symlink() or (source / "mcp-tokens").is_symlink():
        raise ValueError("Refusing symlinked credential directories")
    if not source.is_dir() or not target.is_dir() or source.resolve() == target.resolve():
        raise ValueError("Expected distinct mounted source and target directories")
    if any(target.iterdir()):
        raise ValueError("Target must be empty; never overlay an existing Hermes home")
    for relative in FILES:
        path = source / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("Required authorization file missing or symlinked")
        json.loads(path.read_text())
    auth = json.loads((source / "auth.json").read_text())
    if auth.get("active_provider") != "openai-codex":
        raise ValueError("Unexpected active model provider")
    if set(auth.get("providers", {})) - {"openai-codex"} or set(auth.get("credential_pool", {})) - {"openai-codex"}:
        raise ValueError("Unexpected provider credentials; inspect locally before migrating")
    if not auth.get("providers", {}).get("openai-codex") and not auth.get("credential_pool", {}).get("openai-codex"):
        raise ValueError("OpenAI authorization missing")
    (target / "mcp-tokens").mkdir(mode=0o700)
    for relative in FILES:
        destination = target / relative
        with destination.open("xb") as output, (source / relative).open("rb") as input_file:
            destination.chmod(0o600)
            shutil.copyfileobj(input_file, output)
    print("Transferred only OpenAI and Rohlík authorization files; no agent state copied.")


if __name__ == "__main__":
    migrate(Path("/old"), Path("/new"))
