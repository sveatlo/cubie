import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock


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
        manifest = self.home / "plugins/homeassistant/plugin.yaml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("name: homeassistant\n")

    def initialize(self):
        hermes_init.initialize(self.home, self.config, self.run)

    def test_installs_only_pinned_homeassistant_once(self):
        self.initialize()
        self.initialize()
        self.run.assert_called_once()
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], [
            "/opt/hermes/.venv/bin/hermes", "plugins", "install", "homeassistant",
            "--ref", hermes_init.PLUGIN_REF, "--yes-deps", "--no-enable",
        ])
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 300)
        self.assertEqual(set(p.name for p in self.home.iterdir()), {
            "workspace", "config.yaml", "SOUL.md", ".homeassistant-plugin-ref", "plugins",
        })

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

    def test_does_not_replace_intentionally_empty_identity(self):
        self.initialize()
        (self.home / "SOUL.md").write_text("")
        self.initialize()
        self.assertEqual((self.home / "SOUL.md").read_text(), "")

    def test_failed_plugin_install_blocks_startup_without_success_marker(self):
        self.run.side_effect = RuntimeError("install failed")
        with self.assertRaisesRegex(RuntimeError, "install failed"):
            self.initialize()
        self.assertFalse((self.home / ".homeassistant-plugin-ref").exists())
        self.assertFalse((self.home / "config.yaml").exists())


if __name__ == "__main__":
    unittest.main()
