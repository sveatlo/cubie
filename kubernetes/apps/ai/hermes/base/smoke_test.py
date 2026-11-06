import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url, headers=None):
    with urlopen(Request(url, headers=headers or {}), timeout=20) as response:
        return json.load(response)


def runtime():
    home = Path(os.environ["HERMES_HOME"])
    assert (home / "SOUL.md").is_file()
    assert (home / "config.yaml").is_file()
    assert (home / "plugins/homeassistant/plugin.yaml").is_file()
    assert not any((home / name).exists() for name in (".ssh", ".kube", ".gitconfig", "tools", "alerts"))
    assert not Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists()
    assert not any(os.environ.get(key) for key in (
        "GITHUB_TOKEN", "_HERMES_FORCE_GITHUB_TOKEN", "TALOSCONFIG",
        "PROXMOX_API_URL", "PROXMOX_TOKEN_SECRET", "ALERT_WEBHOOK_TOKEN",
    ))
    request_json("http://127.0.0.1:9119/api/status")
    print("Runtime isolation checks passed.")


def integrations():
    request_json("https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/getMe")
    request_json(os.environ["HASS_URL"].rstrip("/") + "/api/",
                 {"Authorization": "Bearer " + os.environ["HASS_TOKEN"]})
    print("Telegram and Home Assistant read-only authentication checks passed.")
    print("Verify Rohlík tool discovery and Authentik login in the dashboard; no cart or device writes were attempted.")


def api():
    url = "http://127.0.0.1:8642/v1/capabilities"
    key = os.environ["API_SERVER_KEY"]
    if not key.strip():
        raise RuntimeError("API check requires an injected API key.")
    try:
        capabilities = request_json(url, {"Authorization": "Bearer " + key})
        assert capabilities["auth"]["type"] == "bearer"
        assert capabilities["auth"]["required"] is True
        features = capabilities["features"]
        assert all(features[name] is True for name in (
            "run_submission", "run_status", "run_stop", "run_approval_response",
            "run_unknown_resolution", "session_resources",
        ))
        idempotency = features["runs_idempotency"]
        assert idempotency["supported"] is True
        assert idempotency["durable"] is True
        assert idempotency["retention_seconds"] >= 86400
        try:
            request_json(url)
        except HTTPError as error:
            try:
                assert error.code == 401
            finally:
                error.close()
        else:
            raise RuntimeError("API allowed unauthenticated access.")
    except Exception:
        raise RuntimeError("API authentication or capabilities check failed.") from None
    print("API bearer authentication and required capabilities checks passed; no inference attempted.")


def model():
    response = subprocess.run(
        ["hermes", "chat", "--query-file", "-", "--oneshot", "--format", "stream-json",
         "--toolsets", "none", "--max-turns", "1", "--run-budget", "60"],
        input="Reply with exactly SAMWISE_READY. Do not call tools.",
        capture_output=True, text=True, timeout=90,
    )
    results = []
    for line in response.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            results.append(event)
    if response.returncode or not results or results[-1].get("exit_code") or results[-1].get("text", "").strip() != "SAMWISE_READY":
        raise RuntimeError("Model check failed; inspect subscription authentication and quota locally. No fallback attempted.")
    print("OpenAI subscription model check passed.")


if __name__ == "__main__":
    try:
        {"runtime": runtime, "integrations": integrations, "api": api, "model": model}[sys.argv[1]]()
    except Exception:
        raise SystemExit("Smoke check failed; inspect locally without publishing credentials or raw responses.") from None
