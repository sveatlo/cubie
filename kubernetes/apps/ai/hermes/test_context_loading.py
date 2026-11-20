import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent


@unittest.skipUnless(os.environ.get("HERMES_CONTEXT_TESTS") == "1", "requires the pinned Hermes image")
class HermesContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, "/opt/hermes")
        from agent.prompt_builder import build_context_files_prompt, load_soul_md
        cls.build_context = staticmethod(build_context_files_prompt)
        cls.load_soul = staticmethod(load_soul_md)

    def load_script(self, path):
        spec = importlib.util.spec_from_file_location("context_test_init", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_each_profile_loads_its_own_soul_and_workspace_agents_but_not_policy(self):
        initializer = self.load_script(ROOT / "base/init.py")
        for name in ("samwise", "laki", "laki/trader"):
            with self.subTest(profile=name), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                source = ROOT / "instances" / name
                initializer.sync_operating_files(home, source)
                shutil.copyfile(source / "SOUL.md", home / "SOUL.md")
                with patch.dict(os.environ, {"HERMES_HOME": str(home)}):
                    soul = self.load_soul(home_override=home)
                    context = self.build_context(cwd=str(home / "workspace"), home_override=home)
                    self.assertIn((source / "SOUL.md").read_text().strip(), soul)
                    self.assertIn((source / "AGENTS.md").read_text().strip(), context)
                    self.assertNotIn((source / "POLICY.md").read_text().strip(), context)
                    elsewhere = home / "elsewhere"
                    elsewhere.mkdir()
                    outside_context = self.build_context(cwd=str(elsewhere), home_override=home)
                    self.assertIn((source / "SOUL.md").read_text().strip(), outside_context)
                    self.assertNotIn((source / "AGENTS.md").read_text().strip(), outside_context)

    def test_resumed_local_trader_session_keeps_its_old_helper_workspace(self):
        from gateway.session_policy_refresh import _terminal
        initializer = self.load_script(ROOT / "base/init.py")
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory)
            trader = helper / "profiles/trader"
            trader.mkdir(parents=True)
            for home, name in ((helper, "laki"), (trader, "laki/trader")):
                source = ROOT / "instances" / name
                initializer.sync_operating_files(home, source)
                shutil.copyfile(source / "SOUL.md", home / "SOUL.md")
            policy = SimpleNamespace(cwd=str(helper / "workspace"), request_json="{}")
            refreshed = _terminal(policy, {
                "TERMINAL_ENV": "local", "TERMINAL_CWD": str(trader / "workspace"),
            }, picked=())
            self.assertEqual(refreshed["TERMINAL_CWD"], str(helper / "workspace"))
            with patch.dict(os.environ, {"HERMES_HOME": str(trader)}):
                context = self.build_context(cwd=refreshed["TERMINAL_CWD"], home_override=trader)
            self.assertIn((ROOT / "instances/laki/AGENTS.md").read_text().strip(), context)
            self.assertNotIn((ROOT / "instances/laki/trader/AGENTS.md").read_text().strip(), context)
            self.assertIn((ROOT / "instances/laki/trader/SOUL.md").read_text().strip(), context)

    def test_native_trader_creation_works_with_flat_config_mount_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            for source, name in ((ROOT / "base/init.py", "init.py"),
                                 (ROOT / "instances/laki/profile-init.py", "profile-init.py")):
                shutil.copyfile(source, config / name)
            shutil.copytree(ROOT / "instances/laki/trader", config / "trader")
            environment = root / "env"
            environment.mkdir()
            home = root / "home"
            home.mkdir()
            initializer = self.load_script(config / "profile-init.py")
            with patch.dict(os.environ, {"HERMES_HOME": str(home), "HOME": str(home)}):
                profile = initializer.reconcile_profile(home, config / "trader", environment)
                for name, destination in (("SOUL.md", profile / "SOUL.md"),
                                          ("AGENTS.md", profile / "workspace/AGENTS.md"),
                                          ("POLICY.md", profile / "POLICY.md")):
                    self.assertEqual(destination.read_text(), (config / "trader" / name).read_text())
                self.assertFalse((profile / "auth.json").exists())
                (profile / "SOUL.md").write_text("Owner runtime identity\n")
                initializer.reconcile_profile(home, config / "trader", environment)
                self.assertEqual((profile / "SOUL.md").read_text(), "Owner runtime identity\n")

    def test_cron_context_requires_explicit_existing_workdir(self):
        from cron.scheduler import _CronAgentSetup, _construct_cron_agent, _resolve_job_workdir
        with tempfile.TemporaryDirectory() as directory:
            for workdir, skipped in ((directory, False), (directory + "/missing", True), (None, True)):
                with self.subTest(workdir=workdir):
                    job = {"workdir": workdir} if workdir else {}
                    resolved = _resolve_job_workdir(job, "context-test")
                    self.assertEqual(bool(resolved), not skipped)
                    result = _construct_cron_agent(
                        lambda **kwargs: kwargs, job, {}, _CronAgentSetup(model="unused", runtime={}),
                        workdir=resolved, session_id="context-test", session_db=None,
                    )
                    self.assertEqual(result["skip_context_files"], skipped)
                    self.assertTrue(result["load_soul_identity"])


if __name__ == "__main__":
    unittest.main()
