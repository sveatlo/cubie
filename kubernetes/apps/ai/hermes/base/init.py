import json
import os
from pathlib import Path
import shutil
import subprocess

from dotenv import set_key, unset_key


PLUGIN_REFS = {
    "homeassistant": "4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072",
    "camofox": "1138f25c8b7b5a8fb882b3161e248f29abbd1a46",
}


def sync_managed_env(home, source):
    values = {
        path.name: path.read_text()
        for path in source.iterdir()
        if not path.name.startswith(".") and path.is_file()
    }
    marker = home / ".managed-env-keys.json"
    previous = set(json.loads(marker.read_text())) if marker.exists() else set()
    env = home / ".env"
    env.touch(mode=0o600, exist_ok=True)
    env.chmod(0o600)
    for key in previous - values.keys():
        unset_key(env, key)
    for key, value in values.items():
        set_key(env, key, value)
    marker.write_text(json.dumps(sorted(values)) + "\n")
    marker.chmod(0o600)


def initialize(home, config, run=subprocess.run, managed_env=None):
    home.mkdir(parents=True, exist_ok=True)
    (home / "workspace").mkdir(exist_ok=True)
    if managed_env is not None:
        sync_managed_env(home, managed_env)
    soul = home / "SOUL.md"
    if not soul.exists():
        shutil.copyfile(config / "SOUL.md", soul)
        soul.chmod(0o600)
    for name, ref in PLUGIN_REFS.items():
        marker = home / f".{name}-plugin-ref"
        manifest = home / f"plugins/{name}/plugin.yaml"
        if not manifest.is_file() or not marker.exists() or marker.read_text().strip() != ref:
            run([
                "/opt/hermes/.venv/bin/hermes", "plugins", "install", name,
                "--ref", ref, "--yes-deps", "--no-enable",
            ], check=True, stdin=subprocess.DEVNULL, timeout=300)
            if not manifest.is_file():
                raise RuntimeError(f"{name} plugin installation did not publish its manifest")
            marker.write_text(ref + "\n")
            marker.chmod(0o600)
    shutil.copyfile(config / "config.yaml", home / "config.yaml")


if __name__ == "__main__":
    os.umask(0o077)
    initialize(Path(os.environ["HERMES_HOME"]), Path("/config"), managed_env=Path("/managed-env"))
