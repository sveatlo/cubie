from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import tempfile
import unittest


MODULE_PATH = Path(__file__).parent / "instances/laki/profile-init.py"
spec = spec_from_file_location("laki_profile_init", MODULE_PATH)
profile_init = module_from_spec(spec)
spec.loader.exec_module(profile_init)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.default = self.root / "default"
        self.config = self.root / "config"
        self.env = self.root / "env"
        self.default.mkdir()
        self.config.mkdir()
        self.env.mkdir()
        (self.config / "SOUL.md").write_text("Trader seed\n")
        (self.config / "config.yaml").write_text("model:\n  provider: test\n")
        self.env_values = {
            "TELEGRAM_BOT_TOKEN": "trader-token",
            "TELEGRAM_ALLOWED_USERS": "123",
            "TELEGRAM_HOME_CHANNEL": "456",
            "HERMES_LAKI_GATE_CLIENT_TOKEN": "gate-token",
            "HERMES_TIMEZONE": "Europe/Bratislava",
            "HASS_TOKEN": "default-ha-token",
            "GITHUB_TOKEN": "default-github-token",
            "KRAKEN_API_SECRET": "default-kraken-secret",
        }
        for name, value in self.env_values.items():
            (self.env / name).write_text(value)
        self.default_files = {
            "auth.json": b'{"refresh_token":"default-auth"}',
            "state.db": b"default-state",
            "memories/MEMORY.md": b"default-memory",
            "cron/jobs.json": b"default-jobs",
        }
        for name, contents in self.default_files.items():
            path = self.default / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

    def tearDown(self):
        self.tempdir.cleanup()

    def run_native_create(self, calls, fail=False, partial=False):
        def run(command, **kwargs):
            calls.append((command, kwargs))
            home = Path(kwargs["env"]["HERMES_HOME"])
            if not fail or partial:
                (home / "SOUL.md").write_text("Launch-root generic identity\n")
                (home / "logs").mkdir(exist_ok=True)
                (home / "cache").mkdir(exist_ok=True)
                target = home / "profiles/trader"
                target.mkdir(parents=True)
                (target / "SOUL.md").write_text("Generic Hermes identity\n")
                (target / "memories").mkdir()
                (target / "cron").mkdir()
            if fail:
                raise RuntimeError("native profile creation failed")
        return run

    def reconcile(self, run):
        return profile_init.reconcile_profile(self.default, self.config, self.env, run)

    def test_fresh_profile_has_no_default_credentials_or_state(self):
        calls = []
        target = self.reconcile(self.run_native_create(calls))

        self.assertEqual(target, self.default / "profiles/trader")
        self.assertEqual(calls[0][0], [
            "/opt/hermes/.venv/bin/hermes", "profile", "create", "trader",
            "--no-credentials",
        ])
        launch_home = Path(calls[0][1]["env"]["HERMES_HOME"])
        self.assertNotEqual(launch_home, self.default)
        self.assertEqual(launch_home.parent, self.default)
        self.assertEqual(calls[0][1]["env"]["HOME"], str(launch_home))
        self.assertFalse(launch_home.exists())
        self.assertFalse((self.default / "SOUL.md").exists())
        self.assertFalse((self.default / "logs").exists())
        self.assertFalse((self.default / "cache").exists())
        self.assertNotIn("KRAKEN_API_SECRET", calls[0][1]["env"])
        self.assertNotIn("GITHUB_TOKEN", calls[0][1]["env"])
        self.assertFalse((target / "auth.json").exists())
        self.assertFalse((target / "state.db").exists())
        self.assertEqual(list((target / "memories").iterdir()), [])
        self.assertEqual(list((target / "cron").iterdir()), [])
        self.assertEqual((target / "SOUL.md").read_text(), "Trader seed\n")
        self.assertEqual((target / "config.yaml").read_text(), "model:\n  provider: test\n")
        env = (target / ".env").read_text()
        self.assertIn("TELEGRAM_BOT_TOKEN='trader-token'", env)
        self.assertIn("HERMES_TIMEZONE='Europe/Bratislava'", env)
        for secret in ("default-ha-token", "default-github-token", "default-kraken-secret"):
            self.assertNotIn(secret, env)
        self.assertEqual((target / ".env").stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / ".managed-env-keys.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / ".laki-profile-init-v1").stat().st_mode & 0o777, 0o600)
        for name, contents in self.default_files.items():
            self.assertEqual((self.default / name).read_bytes(), contents)

        self.reconcile(self.run_native_create(calls))
        self.assertEqual(len(calls), 1)

    def test_reconcile_preserves_runtime_state_and_custom_or_empty_soul(self):
        calls = []
        target = self.reconcile(self.run_native_create(calls))
        runtime = {
            "state.db": b"runtime-state",
            "memories/MEMORY.md": b"runtime-memory",
            "cron/jobs.json": b"runtime-jobs",
        }
        for name, contents in runtime.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        for soul in ("", "Owner-customized trader identity\n"):
            with self.subTest(soul=soul):
                (target / "SOUL.md").write_text(soul)
                self.reconcile(self.run_native_create(calls))
                self.assertEqual(len(calls), 1)
                for name, contents in runtime.items():
                    self.assertEqual((target / name).read_bytes(), contents)
                self.assertEqual((target / "SOUL.md").read_text(), soul)

    def test_rotation_removes_only_previously_managed_keys(self):
        calls = []
        target = self.reconcile(self.run_native_create(calls))
        env_file = target / ".env"
        env_file.write_text(env_file.read_text() + "OWNER_SETTING=keep\nOLD_MANAGED=remove\n")
        marker = target / ".managed-env-keys.json"
        marker.write_text(json.dumps([
            "TELEGRAM_BOT_TOKEN", "OLD_MANAGED", "HERMES_TIMEZONE",
        ]) + "\n")
        (self.env / "HERMES_TIMEZONE").unlink()
        self.env_values["TELEGRAM_BOT_TOKEN"] = "rotated-token"
        (self.env / "TELEGRAM_BOT_TOKEN").write_text("rotated-token")

        self.reconcile(self.run_native_create(calls))

        contents = env_file.read_text()
        self.assertIn("OWNER_SETTING=keep", contents)
        self.assertNotIn("OLD_MANAGED", contents)
        self.assertNotIn("HERMES_TIMEZONE", contents)
        self.assertIn("TELEGRAM_BOT_TOKEN='rotated-token'", contents)

    def test_unknown_existing_profile_refused(self):
        target = self.default / "profiles/trader"
        target.mkdir(parents=True)
        (target / "state.db").write_bytes(b"owner-state")
        calls = []

        with self.assertRaisesRegex(RuntimeError, "explicit adoption"):
            self.reconcile(self.run_native_create(calls))

        self.assertEqual(calls, [])
        self.assertEqual((target / "state.db").read_bytes(), b"owner-state")

    def test_failed_native_create_leaves_no_profile_and_can_retry(self):
        for partial in (False, True):
            with self.subTest(partial=partial):
                calls = []
                with self.assertRaisesRegex(RuntimeError, "native profile creation failed"):
                    self.reconcile(self.run_native_create(calls, fail=True, partial=partial))
                target = self.default / "profiles/trader"
                self.assertFalse(target.exists())
                self.assertFalse(Path(calls[0][1]["env"]["HERMES_HOME"]).exists())
                self.assertFalse((self.default / ".trader-profile-init-recovery").exists())
        calls = []
        target = self.reconcile(self.run_native_create(calls))
        self.assertEqual((target / "SOUL.md").read_text(), "Trader seed\n")
        self.assertTrue((target / ".laki-profile-init-v1").exists())

    def test_failure_then_owner_profile_cannot_be_adopted_by_retry(self):
        calls = []
        with self.assertRaises(RuntimeError):
            self.reconcile(self.run_native_create(calls, fail=True))
        target = self.default / "profiles/trader"
        target.mkdir(parents=True)
        (target / "state.db").write_bytes(b"owner-state")
        (self.default / ".trader-profile-init-recovery").write_text("stale marker")
        with self.assertRaisesRegex(RuntimeError, "explicit adoption"):
            self.reconcile(self.run_native_create(calls))
        self.assertEqual(len(calls), 1)
        self.assertEqual((target / "state.db").read_bytes(), b"owner-state")
        self.assertFalse((target / ".laki-profile-init-v1").exists())

    def test_symlinked_profile_does_not_modify_default(self):
        profiles = self.default / "profiles"
        profiles.mkdir()
        target = profiles / "trader"
        target.symlink_to(self.default, target_is_directory=True)
        calls = []
        with self.assertRaisesRegex(RuntimeError, "explicit adoption"):
            self.reconcile(self.run_native_create(calls))
        self.assertTrue(target.is_symlink())
        self.assertEqual(calls, [])
        for name, contents in self.default_files.items():
            self.assertEqual((self.default / name).read_bytes(), contents)

    def test_publication_preserves_concurrently_created_owner_profile(self):
        for owner_has_state in (False, True):
            with self.subTest(owner_has_state=owner_has_state):
                calls = []
                target = self.default / "profiles/trader"
                native_create = self.run_native_create(calls)

                def create_with_owner_race(command, **kwargs):
                    native_create(command, **kwargs)
                    target.mkdir(parents=True)
                    if owner_has_state:
                        (target / "state.db").write_bytes(b"owner-state")

                with self.assertRaises(FileExistsError):
                    self.reconcile(create_with_owner_race)
                self.assertTrue(target.is_dir())
                self.assertFalse((target / ".laki-profile-init-v1").exists())
                if owner_has_state:
                    self.assertEqual((target / "state.db").read_bytes(), b"owner-state")
                    (target / "state.db").unlink()
                target.rmdir()
                self.assertFalse(Path(calls[0][1]["env"]["HERMES_HOME"]).exists())

    def test_config_failure_never_publishes_native_profile(self):
        (self.config / "config.yaml").unlink()
        calls = []
        with self.assertRaises(FileNotFoundError):
            self.reconcile(self.run_native_create(calls))
        self.assertFalse((self.default / "profiles/trader").exists())
        self.assertFalse(Path(calls[0][1]["env"]["HERMES_HOME"]).exists())
        (self.config / "config.yaml").write_text("model: test\n")
        target = self.reconcile(self.run_native_create(calls))
        self.assertEqual((target / "config.yaml").read_text(), "model: test\n")

    def test_marked_profile_symlinked_env_does_not_write_default(self):
        calls = []
        target = self.reconcile(self.run_native_create(calls))
        (self.default / ".env").write_text("OWNER_SECRET=untouched\n")
        (target / ".env").unlink()
        (target / ".env").symlink_to(self.default / ".env")
        with self.assertRaisesRegex(RuntimeError, "explicit adoption"):
            self.reconcile(self.run_native_create(calls))
        self.assertEqual((self.default / ".env").read_text(), "OWNER_SECRET=untouched\n")
        self.assertTrue((target / ".env").is_symlink())
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
