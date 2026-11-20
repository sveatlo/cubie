import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


PROFILE_NAME = "trader"
PROFILE_MARKER = ".laki-profile-init-v1"
RECOVERY_MARKER = ".trader-profile-init-recovery"
MANAGED_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USERS",
    "TELEGRAM_HOME_CHANNEL",
    "HERMES_LAKI_GATE_CLIENT_TOKEN",
    "HERMES_TIMEZONE",
}


def _load_sync_managed_env():
    path = Path(__file__).parents[2] / "base/init.py"
    namespace = {"__name__": "profile_init.base_init"}
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    return namespace["sync_managed_env"]


def _write_atomic(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(contents)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _native_environment(default_home):
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL")
        if key in os.environ
    }
    environment.update({"HOME": str(default_home), "HERMES_HOME": str(default_home)})
    return environment


def _prepare_managed_source(source):
    temporary = tempfile.TemporaryDirectory(prefix="laki-trader-env-")
    directory = Path(temporary.name)
    for path in source.iterdir():
        if path.is_file() and path.name in MANAGED_KEYS:
            shutil.copyfile(path, directory / path.name)
    return temporary, directory


def _quarantine_failed_profile(target, profiles, recovery):
    if not target.exists():
        return
    if target.is_dir() and not any(target.iterdir()):
        target.rmdir()
        return
    if not recovery.exists():
        raise RuntimeError("Existing trader profile requires explicit adoption")
    quarantine = profiles / f".trader-profile-recovery-{os.getpid()}"
    suffix = 0
    while quarantine.exists():
        suffix += 1
        quarantine = profiles / f".trader-profile-recovery-{os.getpid()}-{suffix}"
    target.replace(quarantine)


def reconcile_profile(default_home: Path, config_dir: Path, env_dir: Path, run=subprocess.run) -> Path:
    default_home = Path(default_home)
    config_dir = Path(config_dir)
    env_dir = Path(env_dir)
    profiles = default_home / "profiles"
    target = profiles / PROFILE_NAME
    marker = target / PROFILE_MARKER
    recovery = default_home / RECOVERY_MARKER
    profiles.mkdir(parents=True, exist_ok=True)

    if target.exists() and not marker.exists():
        _quarantine_failed_profile(target, profiles, recovery)

    if not target.exists():
        _write_atomic(recovery, json.dumps({"profile": PROFILE_NAME, "version": 1}) + "\n")
        run(
            [
                "/opt/hermes/.venv/bin/hermes",
                "profile",
                "create",
                PROFILE_NAME,
                "--no-credentials",
            ],
            check=True,
            env=_native_environment(default_home),
            stdin=subprocess.DEVNULL,
            timeout=300,
        )

    if not target.is_dir():
        raise RuntimeError("Native profile creation did not publish a trader directory")

    sync_managed_env = _load_sync_managed_env()
    managed_source, filtered_source = _prepare_managed_source(env_dir)
    try:
        sync_managed_env(target, filtered_source)
    finally:
        managed_source.cleanup()

    soul = target / "SOUL.md"
    if not soul.exists():
        temporary = target / ".SOUL.md.profile-init"
        shutil.copyfile(config_dir / "SOUL.md", temporary)
        temporary.chmod(0o600)
        temporary.replace(soul)

    _write_atomic(target / "config.yaml", (config_dir / "config.yaml").read_text())
    _write_atomic(marker, "laki-trader-profile-init-v1\n")
    recovery.unlink(missing_ok=True)
    return target


if __name__ == "__main__":
    os.umask(0o077)
    reconcile_profile(
        Path(os.environ["HERMES_HOME"]),
        Path("/config/trader"),
        Path("/trader-env"),
    )
