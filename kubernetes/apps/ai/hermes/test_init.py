import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from dotenv import dotenv_values


spec = importlib.util.spec_from_file_location("hermes_init", Path(__file__).parent / "base/init.py")
hermes_init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hermes_init)


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "data"
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "config.yaml").write_text("model: initial\n")
        (self.config / "SOUL.md").write_text("Initial Samwise identity\n")
        self.run = Mock(side_effect=self.install_plugin)

    def install_plugin(self, *args, **kwargs):
        name = args[0][3]
        manifest = self.home / f"plugins/{name}/plugin.yaml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(f"name: {name}\n")

    def initialize(self):
        hermes_init.initialize(self.home, self.config, self.run)

    def test_installs_each_pinned_plugin_once(self):
        self.initialize()
        self.initialize()
        self.assertEqual(self.run.call_count, len(hermes_init.PLUGIN_REFS))
        for call, (name, ref) in zip(self.run.call_args_list, hermes_init.PLUGIN_REFS.items()):
            args, kwargs = call
            self.assertEqual(args[0], [
                "/opt/hermes/.venv/bin/hermes", "plugins", "install", name,
                "--ref", ref, "--yes-deps", "--no-enable",
            ])
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["timeout"], 300)
            marker = self.home / f".{name}-plugin-ref"
            self.assertEqual(marker.read_text().strip(), ref)
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_seeds_identity_before_hermes_cli_can_create_its_default(self):
        def install_with_cli_bootstrap(*args, **kwargs):
            soul = self.home / "SOUL.md"
            if not soul.exists():
                soul.write_text("You are Hermes Agent, built by Nous Research.\n")
            self.install_plugin(*args, **kwargs)

        self.run.side_effect = install_with_cli_bootstrap
        self.initialize()
        self.assertEqual((self.home / "SOUL.md").read_text(), "Initial Samwise identity\n")
        self.assertEqual((self.home / "SOUL.md").stat().st_mode & 0o777, 0o600)

    def test_refreshes_config_but_preserves_runtime_identity(self):
        self.initialize()
        soul = self.home / "SOUL.md"
        soul.write_text("Runtime edit\n")
        before = soul.stat()
        (self.config / "SOUL.md").write_text("Changed seed\n")
        (self.config / "config.yaml").write_text("model: updated\n")
        self.initialize()
        self.assertEqual(soul.read_text(), "Runtime edit\n")
        self.assertEqual(soul.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual((self.home / "config.yaml").read_text(), "model: updated\n")

    def test_managed_env_survives_reload_inputs_and_preserves_runtime_settings(self):
        self.home.mkdir()
        env = self.home / ".env"
        env.write_text("# Personal setting\nRUNTIME_SETTING=keep\nTELEGRAM_ALLOWED_USERS=stale\n")
        source = self.root / "managed-env"
        source.mkdir()
        values = {
            "TELEGRAM_ALLOWED_USERS": "221832708",
            "TELEGRAM_BOT_TOKEN": "test-token-with-'quotes'\\and\nnewlines",
            "HASS_URL": "https://home.example.test",
        }
        for key, value in values.items():
            (source / key).write_text(value)
        (source / "..data").mkdir()
        hermes_init.initialize(self.home, self.config, self.run, managed_env=source)
        parsed = dotenv_values(env, interpolate=False)
        self.assertEqual(parsed, {"RUNTIME_SETTING": "keep", **values})
        self.assertIn("# Personal setting", env.read_text())
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.home / ".managed-env-keys.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("test-token", (self.home / ".managed-env-keys.json").read_text())

    def test_managed_env_rotates_and_revokes_only_managed_keys(self):
        source = self.root / "managed-env"
        source.mkdir()
        token = source / "TELEGRAM_BOT_TOKEN"
        token.write_text("old-token")
        hermes_init.initialize(self.home, self.config, self.run, managed_env=source)
        env = self.home / ".env"
        with env.open("a") as output:
            output.write("RUNTIME_SETTING=keep\n")
        token.write_text("new-token")
        hermes_init.initialize(self.home, self.config, self.run, managed_env=source)
        self.assertEqual(dotenv_values(env)["TELEGRAM_BOT_TOKEN"], "new-token")
        token.unlink()
        hermes_init.initialize(self.home, self.config, self.run, managed_env=source)
        self.assertEqual(dotenv_values(env), {"RUNTIME_SETTING": "keep"})

    def test_does_not_replace_intentionally_empty_identity(self):
        self.initialize()
        (self.home / "SOUL.md").write_text("")
        self.initialize()
        self.assertEqual((self.home / "SOUL.md").read_text(), "")

    def test_changed_pin_reinstalls_only_that_plugin(self):
        self.initialize()
        (self.home / ".camofox-plugin-ref").write_text("old\n")
        self.run.reset_mock()
        self.initialize()
        self.run.assert_called_once()
        self.assertEqual(self.run.call_args.args[0][3], "camofox")

    def test_missing_manifest_reinstalls_plugin(self):
        self.initialize()
        (self.home / "plugins/camofox/plugin.yaml").unlink()
        self.run.reset_mock()
        self.initialize()
        self.run.assert_called_once()

    def test_success_without_manifest_blocks_startup(self):
        self.run.side_effect = None
        with self.assertRaisesRegex(RuntimeError, "did not publish its manifest"):
            self.initialize()
        self.assertFalse((self.home / "config.yaml").exists())

    def test_failed_plugin_install_blocks_startup_without_success_marker(self):
        self.run.side_effect = RuntimeError("install failed")
        with self.assertRaisesRegex(RuntimeError, "install failed"):
            self.initialize()
        self.assertFalse((self.home / ".homeassistant-plugin-ref").exists())
        self.assertFalse((self.home / "config.yaml").exists())


if __name__ == "__main__":
    unittest.main()
