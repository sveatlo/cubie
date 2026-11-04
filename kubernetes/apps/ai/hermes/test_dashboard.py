import ipaddress
from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).parent


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor("!Find", lambda loader, node: {"find": loader.construct_sequence(node, deep=True)})
BlueprintLoader.add_constructor("!KeyOf", lambda loader, node: {"key": loader.construct_scalar(node)})


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load((ROOT / "instances/samwise/config.yaml").read_text())
        cls.resources = list(yaml.safe_load_all(subprocess.check_output(["kubectl", "kustomize", str(ROOT)], text=True)))
        cls.authentik = ROOT.parent.parent / "authentik"
        cm = yaml.safe_load((cls.authentik / "config/blueprint-hermes-samwise.yaml").read_text())
        cls.blueprint = yaml.load(cm["data"]["hermes-samwise.yaml"], Loader=BlueprintLoader)

    def resource(self, kind, name):
        return next(r for r in self.resources if r["kind"] == kind and r["metadata"]["name"] == name)

    def entry(self, model):
        return next(e for e in self.blueprint["entries"] if e["model"] == model and e["state"] == "present")

    def test_dashboard_oidc_and_ingress_agree(self):
        dashboard = self.config["dashboard"]
        self.assertEqual(dashboard["public_url"], "https://samwise.${DOMAIN_0}")
        self.assertEqual(dashboard["oauth"]["provider"], "self-hosted")
        oidc = dashboard["oauth"]["self_hosted"]
        self.assertEqual(oidc["issuer"], "https://auth.${DOMAIN_0}/application/o/hermes-samwise/")
        self.assertNotIn("client_secret", oidc)
        for proxy in dashboard["trusted_proxies"]:
            self.assertGreater(ipaddress.ip_network(proxy).prefixlen, 0)
        ingress = self.resource("Ingress", "hermes-dashboard-samwise")
        self.assertEqual(ingress["spec"]["rules"][0]["host"], "samwise.${DOMAIN_0}")
        backend = ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
        self.assertEqual(backend["name"], "hermes-dashboard-samwise")
        self.assertEqual(ingress["metadata"]["annotations"]["traefik.ingress.kubernetes.io/router.tls"], "true")
        self.assertNotIn("traefik.ingress.kubernetes.io/router.middlewares", ingress["metadata"]["annotations"])

    def test_provider_has_exact_callback_public_pkce_and_refresh(self):
        provider = self.entry("authentik_providers_oauth2.oauth2provider")["attrs"]
        oidc = self.config["dashboard"]["oauth"]["self_hosted"]
        self.assertEqual(provider["client_type"], "public")
        self.assertEqual(provider["client_id"], oidc["client_id"])
        self.assertEqual(set(provider["grant_types"]), {"authorization_code", "refresh_token"})
        self.assertEqual(provider["redirect_uris"], [{
            "url": self.config["dashboard"]["public_url"] + "/auth/callback", "matching_mode": "strict",
        }])
        self.assertIn("signing_key", provider)
        self.assertEqual({m["find"][1][1] for m in provider["property_mappings"]}, set(oidc["scopes"].split()))

    def test_owner_only_instance_group_is_the_sole_binding(self):
        group = self.entry("authentik_core.group")
        self.assertEqual(group["identifiers"]["name"], "app_hermes_samwise")
        self.assertEqual(group["attrs"]["users"], [{"find": ["authentik_core.user", ["username", "sveatlo"]]}])
        app = self.entry("authentik_core.application")
        self.assertEqual(app["attrs"]["name"], "Samwise (Hermes)")
        self.assertEqual(app["attrs"]["slug"], "hermes-samwise")
        self.assertEqual(app["attrs"]["policy_engine_mode"], "all")
        self.assertEqual(app["attrs"]["meta_launch_url"], self.config["dashboard"]["public_url"] + "/")
        bindings = [e for e in self.blueprint["entries"] if e["model"] == "authentik_policies.policybinding"]
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["identifiers"]["target"], {"key": app["id"]})
        self.assertEqual(bindings[0]["identifiers"]["group"], {"key": group["id"]})
        self.assertNotIn("user", bindings[0]["identifiers"])
        self.assertTrue(bindings[0]["attrs"]["enabled"])

    def test_legacy_app_and_provider_are_explicitly_removed(self):
        removed = {(e["model"], tuple(e["identifiers"].items())) for e in self.blueprint["entries"] if e["state"] == "absent"}
        self.assertEqual(removed, {
            ("authentik_core.application", (("slug", "hermes"),)),
            ("authentik_providers_oauth2.oauth2provider", (("name", "hermes"),)),
        })

    def test_authentik_mounts_instance_blueprint(self):
        kustomization = yaml.safe_load((self.authentik / "kustomization.yaml").read_text())
        values = yaml.safe_load((self.authentik / "values.yaml").read_text())
        self.assertIn("config/blueprint-hermes-samwise.yaml", kustomization["resources"])
        self.assertIn("authentik-blueprint-hermes-samwise", values["blueprints"]["configMaps"])


if __name__ == "__main__":
    unittest.main()
