from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from test_laki import LAKI, ROOT, load_script, render


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
        self.assertEqual(set(config["mcp_servers"]), {"kraken"})
        kraken = config["mcp_servers"]["kraken"]
        self.assertEqual(kraken["url"], "http://127.0.0.1:8787/mcp")
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

    def test_missing_trader_token_cannot_fall_back_to_helper_token(self):
        module = load_script("profile-init")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trader = root / "trader"
            helper = root / "managed"
            trader.mkdir()
            helper.mkdir()
            (helper / "TELEGRAM_BOT_TOKEN").write_text("helper-token")
            self.assertFalse(module.trader_credentials_ready(trader, helper))

    def test_equal_token_inputs_are_rejected_without_logging_values(self):
        module = load_script("profile-init")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trader = root / "trader"
            helper = root / "managed"
            trader.mkdir()
            helper.mkdir()
            for name, value in {
                "TELEGRAM_BOT_TOKEN": "same-secret",
                "TELEGRAM_ALLOWED_USERS": "123",
                "TELEGRAM_HOME_CHANNEL": "456",
            }.items():
                (trader / name).write_text(value)
            (helper / "TELEGRAM_BOT_TOKEN").write_text("same-secret")
            with self.assertRaisesRegex(RuntimeError, "duplicate trader bot") as caught:
                module.trader_credentials_ready(trader, helper)
            self.assertNotIn("same-secret", str(caught.exception))

    def test_only_one_gateway_remains(self):
        resources = render(ROOT)
        deployments = [r for r in resources if r["kind"] == "Deployment"
                       and r["metadata"].get("name") == "hermes-laki"]
        self.assertEqual(len(deployments), 1)
        self.assertEqual([c["name"] for c in deployments[0]["spec"]["template"]["spec"]["containers"]], ["gateway"])


if __name__ == "__main__":
    unittest.main()
