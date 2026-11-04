from pathlib import Path
import subprocess
import unittest

import yaml


class HomeAssistantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parent
        cls.config = yaml.safe_load((root / "instances/samwise/config.yaml").read_text())
        resources = list(yaml.safe_load_all(subprocess.check_output(["kubectl", "kustomize", str(root)], text=True)))
        deployment = next(r for r in resources if r["kind"] == "Deployment")
        cls.pod = deployment["spec"]["template"]["spec"]

    def test_tools_without_autonomous_ha_events(self):
        self.assertIn("homeassistant", self.config["plugins"]["enabled"])
        self.assertIs(self.config["platforms"]["homeassistant"]["enabled"], False)
        self.assertEqual(self.config["approvals"]["mode"], "manual")
        for mode in ("unattended_mode", "single_query_mode", "cron_mode"):
            self.assertEqual(self.config["approvals"][mode], "deny")
        for platform in ("telegram", "cli", "api_server"):
            self.assertEqual(self.config["platform_toolsets"][platform], [
                "terminal", "file", "homeassistant", "mcp-rohlik-mcp", "mcp-mealie", "camofox",
            ])

    def test_only_gateway_receives_full_ha_credentials(self):
        expected = [
            {"secretRef": {"name": "hermes-samwise-homeassistant"}},
            {"prefix": "_HERMES_FORCE_", "secretRef": {"name": "hermes-samwise-homeassistant"}},
        ]
        for container in self.pod["containers"] + self.pod["initContainers"]:
            refs = [ref for ref in container.get("envFrom", [])
                    if ref.get("secretRef", {}).get("name") == "hermes-samwise-homeassistant"]
            self.assertEqual(refs, expected if container["name"] == "gateway" else [])
            self.assertFalse(any("HASS" in env["name"] for env in container.get("env", [])))


if __name__ == "__main__":
    unittest.main()
