import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, "/opt/hermes")


def runtime():
    home = Path(os.environ["HERMES_HOME"])
    for name in ("kubectl", "talosctl"):
        subprocess.run([str(home / "tools" / name), "version", "--client"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    for name in ("id_ed25519", "config", "known_hosts"):
        assert stat.S_IMODE((home / ".ssh" / name).stat().st_mode) == 0o600
    config = subprocess.check_output(["ssh", "-G", "test.invalid"], stderr=subprocess.DEVNULL, text=True)
    assert "stricthostkeychecking true" in config and "batchmode yes" in config
    for attempt in range(30):
        try:
            with urlopen("http://127.0.0.1:9222/json/version", timeout=2):
                break
        except OSError:
            if attempt == 29:
                raise SystemExit("Chromium sidecar CDP endpoint did not become ready") from None
            time.sleep(1)
    from tools.browser_tool import browser_navigate
    from tools.browser_tool_lifecycle import cleanup_all_browsers

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<title>Cubie browser smoke test</title><p>Chromium ready</p>")

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = json.loads(browser_navigate(f"http://127.0.0.1:{server.server_port}", task_id="smoke"))
        if not result.get("success") or result.get("title") != "Cubie browser smoke test":
            raise RuntimeError("Local Chromium smoke test failed; inspect browser runtime locally")
    finally:
        cleanup_all_browsers()
        server.shutdown()
        server.server_close()
    print("Runtime checks passed: kubectl, talosctl, SSH permissions/strict verification, local Chromium.")


def model():
    response = subprocess.run(
        ["hermes", "chat", "--query-file", "-", "--oneshot", "--format", "stream-json",
         "--toolsets", "none", "--max-turns", "1", "--run-budget", "60"],
        input="Reply with exactly HERMES_READY. Do not call tools.", capture_output=True, text=True, timeout=90)
    results = []
    for line in response.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            results.append(event)
    if response.returncode or not results or results[-1].get("exit_code") or results[-1].get("text", "").strip() != "HERMES_READY":
        raise SystemExit("Model smoke test failed. Check subscription eligibility, requested model, auth and quota locally. No fallback attempted.")
    print("OpenAI subscription model smoke test passed.")


def integrations():
    checks = [
        ("Kubernetes", lambda: subprocess.run(["kubectl", "auth", "can-i", "get", "nodes", "--quiet"],
                                              check=True, capture_output=True, timeout=20)),
        ("Talos", lambda: subprocess.run(["talosctl", "--nodes", "10.69.10.236", "get", "machinestatus"],
                                         check=True, capture_output=True, timeout=30)),
        ("GitHub", lambda: request_json("https://api.github.com/repos/sveatlo/cubie",
                                        {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]})),
        ("Telegram", lambda: request_json("https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/getMe")),
    ]
    base = os.environ["PROXMOX_API_URL"].rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("Proxmox API URL must be HTTPS, without embedded credentials")
    context = proxmox_tls_context()
    checks.append(("Proxmox", lambda: request_json(base + "/api2/json/nodes",
        {"Authorization": "PVEAPIToken=" + os.environ["PROXMOX_TOKEN_ID"] + "=" + os.environ["PROXMOX_TOKEN_SECRET"]}, context)))
    for name, check in checks:
        try:
            check()
        except Exception:
            raise SystemExit(f"{name} connectivity/authentication check failed; inspect credentials, permissions and TLS locally") from None
        print(f"{name} read-only connectivity check passed.")
    workspace = Path("/opt/data/workspace/cubie")
    if not workspace.exists():
        subprocess.run(["git", "clone", "https://github.com/sveatlo/cubie.git", str(workspace)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)


def proxmox_tls_context():
    verify = os.environ.get("PROXMOX_VERIFY_TLS", "true").lower()
    if verify not in ("true", "false"):
        raise ValueError("PROXMOX_VERIFY_TLS must be true or false")
    context = ssl.create_default_context(cafile=(os.environ.get("PROXMOX_CA_FILE") or None) if verify == "true" else None)
    if verify == "false":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def request_json(url, headers=None, context=None):
    with urlopen(Request(url, headers=headers or {}), timeout=30, context=context) as response:
        return json.load(response)


if __name__ == "__main__":
    {"runtime": runtime, "model": model, "integrations": integrations}[sys.argv[1] if len(sys.argv) > 1 else "runtime"]()
