import hashlib
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "opt/data"
        self.config = self.root / "config"
        self.config.mkdir()
        (self.root / "ssh").mkdir()
        (self.home / "tools").mkdir(parents=True)
        for name, text in {
            "config.yaml": "model: initial\n",
            "SOUL.md": "Initial identity\n",
            "id_ed25519.pub": "test public key\n",
            "ssh-config": "Host *\n",
            "known_hosts": "",
        }.items():
            (self.config / name).write_text(text)
        (self.root / "ssh/id_ed25519").write_text("test private-key fixture\n")
        for name in ("kubectl", "talosctl"):
            (self.home / "tools" / name).write_bytes(name.encode())
        self.script = Path(__file__).with_name("init.py")

    def initialize(self):
        def mapped(value):
            path = Path(value)
            if path.is_absolute() and not path.is_relative_to(self.root):
                return self.root / path.relative_to("/")
            return path

        digests = {
            b"kubectl": "924eb50779153f20cb668117d141440b95df2f325a64452d78dff9469145e277",
            b"talosctl": "4c41a3b10b075292e64b182283d558e9d8e935f43239de1ed4e4b14359593efb",
        }
        copyfile = shutil.copyfile
        with patch("pathlib.Path", side_effect=mapped), \
                patch("shutil.copyfile", side_effect=lambda src, dst: copyfile(mapped(src), mapped(dst))), \
                patch.object(hashlib, "sha256", side_effect=lambda data: Mock(hexdigest=lambda: digests[data])), \
                patch("urllib.request.urlopen", side_effect=AssertionError("unexpected tool download")):
            runpy.run_path(str(self.script))

    def test_seeds_once_and_preserves_runtime_edits_on_redeploy(self):
        self.initialize()
        soul = self.home / "SOUL.md"
        self.assertEqual(soul.read_text(), "Initial identity\n")
        soul.write_text("Agent-edited identity\n")
        soul.chmod(0o600)
        before = soul.stat()
        (self.config / "SOUL.md").write_text("Changed Git template\n")
        (self.config / "config.yaml").write_text("model: updated\n")
        self.initialize()
        self.assertEqual(soul.read_text(), "Agent-edited identity\n")
        self.assertEqual(soul.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(soul.stat().st_mode, before.st_mode)
        self.assertEqual((self.home / "config.yaml").read_text(), "model: updated\n")

    def test_existing_empty_soul_is_not_reseeded(self):
        (self.home / "SOUL.md").write_text("")
        self.initialize()
        self.assertEqual((self.home / "SOUL.md").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
