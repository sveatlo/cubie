from pathlib import Path
import unittest

import yaml

from test_dashboard import BlueprintLoader


class LakiAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[2] / "authentik/config/blueprint-hermes-samwise.yaml"
        config = yaml.safe_load(path.read_text())
        cls.entries = yaml.load(config["data"]["hermes-samwise.yaml"], Loader=BlueprintLoader)["entries"]

    def test_laki_has_owner_only_group_and_strict_dashboard_callback(self):
        entries = {entry["id"]: entry for entry in self.entries if "id" in entry}
        group = entries["hermes-laki-access"]
        self.assertEqual(group["identifiers"]["name"], "app_hermes_laki")
        self.assertEqual(group["attrs"]["users"], [
            {"find": ["authentik_core.user", ["username", "sveatlo"]]},
        ])
        provider = entries["hermes-laki-provider"]["attrs"]
        self.assertEqual(provider["client_id"], "hermes-laki-dashboard")
        self.assertEqual(provider["client_type"], "public")
        self.assertEqual(provider["redirect_uris"], [{
            "url": "https://laki.${DOMAIN_0}/auth/callback", "matching_mode": "strict",
        }])
        browser = entries["hermes-laki-browser-provider"]["attrs"]
        self.assertEqual(browser["external_host"], "https://laki-browser.${DOMAIN_0}")
        self.assertEqual(browser["mode"], "forward_single")
        for app in ("hermes-laki-application", "hermes-laki-browser-application"):
            bindings = [entry for entry in self.entries
                        if entry["model"] == "authentik_policies.policybinding"
                        and entry["identifiers"]["target"] == {"key": app}]
            self.assertEqual(len(bindings), 1)
            self.assertEqual(bindings[0]["identifiers"]["group"], {"key": "hermes-laki-access"})
            self.assertTrue(bindings[0]["attrs"]["enabled"])

    def test_single_outpost_assignment_preserves_both_browser_providers(self):
        outposts = [entry for entry in self.entries if entry["model"] == "authentik_outposts.outpost"]
        self.assertEqual(len(outposts), 1)
        self.assertEqual(outposts[0]["attrs"]["providers"], [
            {"key": "hermes-samwise-browser-provider"},
            {"key": "hermes-laki-browser-provider"},
        ])


if __name__ == "__main__":
    unittest.main()
