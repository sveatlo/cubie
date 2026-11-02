from pathlib import Path
import unittest

import yaml


class HomeAssistantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parent
        cls.config = yaml.safe_load((root / "config.yaml").read_text())
        resources = list(yaml.safe_load_all((root / "resources.yaml").read_text()))
        deployment = next(r for r in resources if r["kind"] == "Deployment" and r["metadata"]["name"] == "hermes")
        cls.pod = deployment["spec"]["template"]["spec"]

    def test_telegram_has_tools_without_autonomous_ha_events(self):
        self.assertIn("homeassistant", self.config["plugins"]["enabled"])
        self.assertIn("homeassistant", self.config["platform_toolsets"]["telegram"])
        self.assertIs(self.config["platforms"]["homeassistant"]["enabled"], False)
        self.assertEqual(self.config["approvals"]["mode"], "manual")
        for mode in ("unattended_mode", "single_query_mode", "cron_mode"):
            self.assertEqual(self.config["approvals"][mode], "deny")

    def test_only_gateway_receives_ha_and_terminal_override_credentials(self):
        expected = [
            {"secretRef": {"name": "hermes-homeassistant"}},
            {"prefix": "_HERMES_FORCE_", "secretRef": {"name": "hermes-homeassistant"}},
        ]
        for container in self.pod["containers"] + self.pod["initContainers"]:
            refs = [ref for ref in container.get("envFrom", [])
                    if ref.get("secretRef", {}).get("name") == "hermes-homeassistant"]
            self.assertEqual(refs, expected if container["name"] == "gateway" else [])
            self.assertFalse(any("HASS" in env["name"] for env in container.get("env", [])))


if __name__ == "__main__":
    unittest.main()
