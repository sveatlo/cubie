import json
from pathlib import Path
import tempfile
import unittest

import migrate_auth


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "old"
        self.target = self.root / "new"
        self.source.mkdir()
        self.target.mkdir()
        (self.source / "mcp-tokens").mkdir()
        self.auth = {
            "active_provider": "openai-codex",
            "providers": {},
            "credential_pool": {"openai-codex": [{"access_token": "synthetic-token"}]},
        }
        for relative in migrate_auth.FILES:
            (self.source / relative).write_text(json.dumps(self.auth if relative == "auth.json" else {"synthetic": relative}))
        for name in ("SOUL.md", ".env", "state.db", "old-memory.md"):
            (self.source / name).write_text("must not migrate")
        (self.source / "mcp-tokens/another-server.json").write_text("{}")
        (self.source / "mcp-tokens/rohlik-mcp.json.refresh.lock").touch()

    def test_only_explicit_authorization_files_are_copied(self):
        migrate_auth.migrate(self.source, self.target)
        actual = {str(p.relative_to(self.target)) for p in self.target.rglob("*") if p.is_file()}
        self.assertEqual(actual, set(migrate_auth.FILES))
        for relative in actual:
            self.assertEqual((self.target / relative).read_bytes(), (self.source / relative).read_bytes())
            self.assertEqual((self.target / relative).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.target / "mcp-tokens").stat().st_mode & 0o777, 0o700)

    def test_nonempty_destination_is_never_overwritten(self):
        (self.target / "auth.json").write_text("existing")
        with self.assertRaisesRegex(ValueError, "Target must be empty"):
            migrate_auth.migrate(self.source, self.target)
        self.assertEqual((self.target / "auth.json").read_text(), "existing")

    def test_missing_or_corrupt_source_fails_before_any_copy(self):
        for invalid in (None, "not json"):
            with self.subTest(invalid=invalid):
                file = self.source / migrate_auth.FILES[-1]
                file.unlink(missing_ok=True)
                if invalid is not None:
                    file.write_text(invalid)
                with self.assertRaises(ValueError):
                    migrate_auth.migrate(self.source, self.target)
                self.assertEqual(list(self.target.iterdir()), [])

    def test_other_model_credentials_are_not_migrated(self):
        self.auth["credential_pool"]["other-provider"] = ["synthetic-other-token"]
        (self.source / "auth.json").write_text(json.dumps(self.auth))
        with self.assertRaisesRegex(ValueError, "Unexpected provider credentials"):
            migrate_auth.migrate(self.source, self.target)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_symlinks_are_rejected_before_any_copy(self):
        file = self.source / migrate_auth.FILES[-1]
        file.unlink()
        file.symlink_to(self.source / "auth.json")
        with self.assertRaisesRegex(ValueError, "missing or symlinked"):
            migrate_auth.migrate(self.source, self.target)
        self.assertEqual(list(self.target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
