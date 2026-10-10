import os
from pathlib import Path
import sys

sys.path.insert(0, "/opt/hermes")
from hermes_cli.browser_runtime import chromium_executable

Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)
executable = chromium_executable()
if not executable:
    raise SystemExit("Packaged Chromium is missing from the pinned image")
os.execv(executable, [executable, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                     "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222",
                     "--user-data-dir=/tmp/browser/profile", "--no-first-run", "--no-default-browser-check"])
