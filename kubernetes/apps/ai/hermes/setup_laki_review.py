import fcntl
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


NAME = "laki-ha-daily-review"
SCHEDULE = "0 8 * * *"
def provision(store, timezone, prompt):
    ZoneInfo(timezone)
    matches = [job for job in store.list_jobs(include_disabled=True) if job.get("name") == NAME]
    if len(matches) > 1:
        raise RuntimeError("Duplicate daily review jobs; resolve them by ID before provisioning.")
    if not matches:
        return store.create_job(
            name=NAME, prompt=prompt, schedule=SCHEDULE, timezone=timezone,
            deliver="telegram", paused=True, paused_reason="Awaiting provisioning verification",
        )
    job = matches[0]
    expected = {"prompt": prompt, "timezone": timezone, "deliver": "telegram"}
    changes = {key: value for key, value in expected.items() if job.get(key) != value}
    if job.get("schedule", {}).get("expr") != SCHEDULE:
        changes["schedule"] = SCHEDULE
    if changes:
        result = store.update_job(job["id"], changes)
        if result is None:
            raise RuntimeError("Daily review disappeared during provisioning.")
        return result
    return job


def main():
    sys.path.insert(0, "/opt/hermes")
    import hermes_yaml as yaml
    home = Path(os.environ["HERMES_HOME"])
    config = yaml.safe_load((home / "config.yaml").read_text())
    client = config.get("dashboard", {}).get("oauth", {}).get("self_hosted", {}).get("client_id")
    if client != "hermes-laki-dashboard":
        raise RuntimeError("Run this only in Laki's gateway with its configured Hermes home.")
    if not os.environ.get("TELEGRAM_HOME_CHANNEL", "").strip():
        raise RuntimeError("Laki's Telegram home channel is required before provisioning.")
    request = Request(os.environ["HASS_URL"].rstrip("/") + "/api/config",
                      headers={"Authorization": "Bearer " + os.environ["HASS_TOKEN"]})
    with urlopen(request, timeout=20) as response:
        timezone = json.load(response)["time_zone"]
    ZoneInfo(timezone)
    from cron import jobs
    with (home / ".laki-review-provision.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        job = provision(jobs, timezone, Path("/config/daily-review.md").read_text())
    print(json.dumps({key: job.get(key) for key in (
        "id", "name", "timezone", "deliver", "state", "next_run_at",
    )}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Daily review setup failed; inspect locally without publishing credentials.") from None
