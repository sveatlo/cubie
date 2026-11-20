from importlib.util import module_from_spec, spec_from_file_location
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from test_laki import LAKI, ROOT, load_script, render


def load_script_from(path):
    spec = spec_from_file_location("mounted_profile_init", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KrakenTests(unittest.TestCase):
    def test_helper_has_no_kraken_registration_or_secret_projection(self):
        config = yaml.safe_load((LAKI / "config.yaml").read_text())
        self.assertNotIn("kraken", config.get("mcp_servers", {}))
        resources = render(LAKI)
        deployment = next(r for r in resources if r["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        dumped = yaml.safe_dump(pod)
        self.assertNotIn("hermes-laki-kraken", dumped)
        self.assertNotIn("KRAKEN_", dumped)
        self.assertNotIn("kraken-mcp", (LAKI / "operator-init.py").read_text())

    def test_trader_has_only_guarded_kraken_without_raw_exchange_env(self):
        config = yaml.safe_load((LAKI / "trader/config.yaml").read_text())
        self.assertEqual(config["terminal"]["cwd"], "/opt/data/profiles/trader/workspace")
        self.assertEqual(set(config["mcp_servers"]), {"kraken"})
        kraken = config["mcp_servers"]["kraken"]
        self.assertEqual(kraken["url"], "http://hermes-laki-kraken-gate:8000/mcp")
        self.assertEqual(kraken["headers"], {
            "Authorization": "Bearer ${HERMES_LAKI_GATE_CLIENT_TOKEN}",
        })
        self.assertEqual(kraken["trust"], "full")
        self.assertNotIn("env", kraken)
        self.assertNotIn("KRAKEN_", yaml.safe_dump(config))

    def test_trader_inputs_are_scoped_to_init_and_notifier_not_gateway_env(self):
        resources = render(ROOT)
        deployment = next(r for r in resources if r["kind"] == "Deployment"
                           and r["metadata"]["name"] == "hermes-laki")
        pod = deployment["spec"]["template"]["spec"]
        gateway = next(c for c in pod["containers"] if c["name"] == "gateway")
        gateway_dump = yaml.safe_dump(gateway)
        self.assertNotIn("hermes-laki-trader", gateway_dump)
        self.assertNotIn("trader-env", gateway_dump)
        profile_init = next(c for c in pod["initContainers"] if c["name"] == "profile-configure")
        self.assertIn({"name": "trader-env", "mountPath": "/trader-env", "readOnly": True},
                      profile_init["volumeMounts"])
        self.assertIn({"name": "config", "mountPath": "/config", "readOnly": True},
                      profile_init["volumeMounts"])
        self.assertIn("profile-init.py", yaml.safe_dump(next(r for r in resources if r["kind"] == "ConfigMap")["data"]))

    def test_trader_credentials_are_reconciled_without_blocking_helper(self):
        module = load_script("profile-init")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "profile"
            config = root / "config"
            trader = root / "trader-env"
            helper = root / "managed-env"
            for path in (target, config, trader, helper):
                path.mkdir()
            (config / "SOUL.md").write_text("Trader\n")
            (config / "AGENTS.md").write_text("Read own policy.\n")
            (config / "POLICY.md").write_text("Analysis only.\n")
            (config / "config.yaml").write_text("terminal:\n  cwd: /opt/data/profiles/trader/workspace\n")
            (target / ".env").write_text("TELEGRAM_BOT_TOKEN='stale'\nTELEGRAM_ALLOWED_USERS='123'\n")
            (target / ".managed-env-keys.json").write_text(
                '["TELEGRAM_ALLOWED_USERS", "TELEGRAM_BOT_TOKEN"]\n'
            )
            (target / "SOUL.md").write_text("Trader\n")
            (target / "config.yaml").write_text("old\n")
            (helper / "TELEGRAM_BOT_TOKEN").write_text("helper-token")
            for case in ({}, {"TELEGRAM_BOT_TOKEN": "partial"}, {
                "TELEGRAM_BOT_TOKEN": "helper-token",
                "TELEGRAM_ALLOWED_USERS": "123",
                "TELEGRAM_HOME_CHANNEL": "456",
            }):
                for path in trader.iterdir():
                    path.unlink()
                for name, value in case.items():
                    (trader / name).write_text(value)
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    module._configure(target, config, trader, helper)
                self.assertNotIn("stale", (target / ".env").read_text())
                self.assertNotIn("partial", (target / ".env").read_text())
                self.assertNotIn("helper-token", (target / ".env").read_text())
                self.assertNotIn("partial", output.getvalue())
                self.assertNotIn("helper-token", output.getvalue())
                self.assertEqual((helper / "TELEGRAM_BOT_TOKEN").read_text(), "helper-token")

    def test_profile_init_loads_base_helper_from_mounted_config_layout(self):
        module = load_script("profile-init")
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            config.mkdir()
            (config / "profile-init.py").write_text((LAKI / "profile-init.py").read_text())
            (config / "init.py").write_text((ROOT / "base/init.py").read_text())
            mounted = load_script_from(config / "profile-init.py")
            initializer = mounted._load_base_init()
            self.assertTrue(callable(initializer.sync_managed_env))
            self.assertTrue(callable(initializer.sync_operating_files))

    def test_trader_uses_profile_owned_workspace(self):
        config = yaml.safe_load((LAKI / "trader/config.yaml").read_text())
        self.assertEqual(config["terminal"]["cwd"], "/opt/data/profiles/trader/workspace")

    def test_only_one_gateway_remains(self):
        resources = render(ROOT)
        deployments = [r for r in resources if r["kind"] == "Deployment"
                       and r["metadata"].get("name") == "hermes-laki"]
        self.assertEqual(len(deployments), 1)
        self.assertEqual([c["name"] for c in deployments[0]["spec"]["template"]["spec"]["containers"]], ["gateway"])


if __name__ == "__main__":
    unittest.main()
