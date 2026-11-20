import ctypes
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


PROFILE_NAME = "trader"
PROFILE_MARKER = ".laki-profile-init-v1"
MARKER_CONTENT = "laki-trader-profile-init-v1\n"
BOT_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USERS",
    "TELEGRAM_HOME_CHANNEL",
}
MANAGED_KEYS = BOT_KEYS | {"HERMES_LAKI_GATE_CLIENT_TOKEN", "HERMES_TIMEZONE", "CAMOFOX_URL"}


def trader_credentials_ready(trader_env, helper_env):
    trader_values = {
        path.name: path.read_text()
        for path in Path(trader_env).iterdir()
        if path.name in MANAGED_KEYS and path.is_file()
    }
    bot_values = {key: trader_values[key] for key in BOT_KEYS if trader_values.get(key, "").strip()}
    if len(bot_values) == len(BOT_KEYS):
        helper_token = Path(helper_env) / "TELEGRAM_BOT_TOKEN"
        if helper_token.is_file() and helper_token.read_text() == bot_values["TELEGRAM_BOT_TOKEN"]:
            raise RuntimeError("duplicate trader bot credential")
        return True
    return False


def _load_sync_managed_env():
    path = Path(__file__).parents[2] / "base/init.py"
    spec = spec_from_file_location("laki_profile_base_init", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.sync_managed_env


def _write_atomic(path, contents):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _native_environment(home):
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL")
        if key in os.environ
    }
    environment.update({"HOME": str(home), "HERMES_HOME": str(home)})
    return environment


def _configure(target, config_dir, env_dir, helper_env, fresh=False):
    for name in ("SOUL.md", "config.yaml", ".env", ".managed-env-keys.json", PROFILE_MARKER):
        path = target / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError("Trader managed files require explicit adoption")
    with tempfile.TemporaryDirectory(prefix="laki-trader-env-") as directory:
        source = Path(directory)
        ready = trader_credentials_ready(env_dir, helper_env)
        if os.environ.get("CAMOFOX_URL"):
            (source / "CAMOFOX_URL").write_text(os.environ["CAMOFOX_URL"])
        for path in env_dir.iterdir() if env_dir.is_dir() else ():
            if path.name in MANAGED_KEYS and path.is_file() and (path.name not in BOT_KEYS or ready):
                destination = source / path.name
                destination.touch(mode=0o600)
                shutil.copyfile(path, destination)
        _load_sync_managed_env()(target, source)
    if fresh or not (target / "SOUL.md").exists():
        _write_atomic(target / "SOUL.md", (config_dir / "SOUL.md").read_text())
    _write_atomic(target / "config.yaml", (config_dir / "config.yaml").read_text())
    _write_atomic(target / PROFILE_MARKER, MARKER_CONTENT)


def _publish(staged, target):
    # Linux RENAME_NOREPLACE keeps a concurrently created owner directory intact.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(staged), -100, os.fsencode(target), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def reconcile_profile(default_home: Path, config_dir: Path, env_dir: Path,
                      run=subprocess.run, helper_env: Path | None = None) -> Path:
    default_home = Path(default_home)
    config_dir = Path(config_dir)
    env_dir = Path(env_dir)
    helper_env = Path(helper_env) if helper_env is not None else Path("/nonexistent")
    profiles = default_home / "profiles"
    target = profiles / PROFILE_NAME
    if profiles.is_symlink():
        raise RuntimeError("Profiles directory requires explicit adoption")
    profiles.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise RuntimeError("Existing trader profile requires explicit adoption")
    if target.exists():
        marker = target / PROFILE_MARKER
        if (not target.is_dir() or marker.is_symlink() or not marker.is_file()
                or marker.read_text() != MARKER_CONTENT):
            raise RuntimeError("Existing trader profile requires explicit adoption")
        _configure(target, config_dir, env_dir, helper_env)
        return target

    with tempfile.TemporaryDirectory(prefix=".trader-profile-init-", dir=default_home) as directory:
        home = Path(directory)
        run(
            ["/opt/hermes/.venv/bin/hermes", "profile", "create", PROFILE_NAME, "--no-credentials"],
            check=True,
            env=_native_environment(home),
            stdin=subprocess.DEVNULL,
            timeout=300,
        )
        staged = home / "profiles" / PROFILE_NAME
        if (home / "profiles").is_symlink() or staged.is_symlink() or not staged.is_dir():
            raise RuntimeError("Native profile creation did not publish a trader directory")
        _configure(staged, config_dir, env_dir, helper_env, fresh=True)
        _publish(staged, target)
    return target


if __name__ == "__main__":
    os.umask(0o077)
    reconcile_profile(Path(os.environ["HERMES_HOME"]), Path("/config/trader"), Path("/trader-env"),
                      helper_env=Path("/managed-env"))
