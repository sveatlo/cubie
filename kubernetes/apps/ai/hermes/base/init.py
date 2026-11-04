import os
from pathlib import Path
import shutil
import subprocess


PLUGIN_REF = "4d492b1dc5326af3e38bb2cf3e4b9ad6d65f0072"


def initialize(home, config, run=subprocess.run):
    home.mkdir(parents=True, exist_ok=True)
    (home / "workspace").mkdir(exist_ok=True)
    marker = home / ".homeassistant-plugin-ref"
    manifest = home / "plugins/homeassistant/plugin.yaml"
    if not manifest.is_file() or not marker.exists() or marker.read_text().strip() != PLUGIN_REF:
        run([
            "/opt/hermes/.venv/bin/hermes", "plugins", "install", "homeassistant",
            "--ref", PLUGIN_REF, "--yes-deps", "--no-enable",
        ], check=True, stdin=subprocess.DEVNULL, timeout=300)
        if not manifest.is_file():
            raise RuntimeError("Home Assistant plugin installation did not publish its manifest")
        marker.write_text(PLUGIN_REF + "\n")
        marker.chmod(0o600)
    shutil.copyfile(config / "config.yaml", home / "config.yaml")
    soul = home / "SOUL.md"
    if not soul.exists():
        shutil.copyfile(config / "SOUL.md", soul)
        soul.chmod(0o600)


if __name__ == "__main__":
    os.umask(0o077)
    initialize(Path(os.environ["HERMES_HOME"]), Path("/config"))
