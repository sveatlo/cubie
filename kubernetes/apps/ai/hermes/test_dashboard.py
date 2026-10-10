import ipaddress
from pathlib import Path
import unittest

import yaml


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor("!Find", lambda loader, node: {"find": loader.construct_sequence(node, deep=True)})
BlueprintLoader.add_constructor("!KeyOf", lambda loader, node: {"key": loader.construct_scalar(node)})


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parent
        cls.config = yaml.safe_load((cls.root / "config.yaml").read_text())
        cls.resources = list(yaml.safe_load_all((cls.root / "resources.yaml").read_text()))
        cls.authentik = cls.root.parent.parent / "authentik"
        cm = yaml.safe_load((cls.authentik / "config/blueprint-hermes.yaml").read_text())
        cls.blueprint = yaml.load(cm["data"]["hermes.yaml"], Loader=BlueprintLoader)

    def resource(self, kind, name):
        return next(r for r in self.resources if r["kind"] == kind and r["metadata"]["name"] == name)

    def entry(self, model):
        return next(e for e in self.blueprint["entries"] if e["model"] == model)

    def test_dashboard_uses_oidc_with_bounded_proxy_trust(self):
        dashboard = self.config["dashboard"]
        self.assertEqual(dashboard["public_url"], "https://hermes.${DOMAIN_0}")
        self.assertEqual(dashboard["oauth"]["provider"], "self-hosted")
        self.assertEqual(dashboard["oauth"]["self_hosted"]["issuer"],
                         "https://auth.${DOMAIN_0}/application/o/hermes/")
        for proxy in dashboard["trusted_proxies"]:
            self.assertGreater(ipaddress.ip_network(proxy).prefixlen, 0)
        self.assertNotIn("client_secret", dashboard["oauth"]["self_hosted"])

    def test_ingress_is_https_lan_only_and_service_is_internal(self):
        ingress = self.resource("Ingress", "hermes-dashboard")
        annotations = ingress["metadata"]["annotations"]
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/router.middlewares"],
                         "traefik-lan-only@kubernetescrd")
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/router.entrypoints"], "websecure")
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/router.tls"], "true")
        self.assertEqual(ingress["spec"]["ingressClassName"], "traefik")
        self.assertEqual(ingress["spec"]["rules"][0]["host"], "hermes.${DOMAIN_0}")
        service = self.resource("Service", "hermes-dashboard")
        self.assertEqual(service["spec"].get("type", "ClusterIP"), "ClusterIP")
        self.assertEqual(service["spec"]["ports"][0]["targetPort"], "dashboard")

    def test_native_supervisor_is_enabled_without_an_auth_bypass(self):
        pod = self.resource("Deployment", "hermes")["spec"]["template"]["spec"]
        self.assertEqual(len(pod["containers"]), 3)
        gateway = next(c for c in pod["containers"] if c["name"] == "gateway")
        env = {v["name"]: v.get("value") for v in gateway["env"]}
        self.assertEqual(env["HERMES_DASHBOARD"], "true")
        self.assertEqual(env["HERMES_DASHBOARD_HOST"], "0.0.0.0")
        self.assertEqual(env["HERMES_DASHBOARD_PORT"], "9119")
        self.assertNotIn("HERMES_DASHBOARD_INSECURE", env)
        self.assertNotIn("command", gateway)
        self.assertEqual(gateway["args"], ["gateway", "run"])
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertGreater(gateway[probe]["timeoutSeconds"], 2)

    def test_public_client_callback_signing_and_refresh_match_hermes(self):
        provider = self.entry("authentik_providers_oauth2.oauth2provider")["attrs"]
        oidc = self.config["dashboard"]["oauth"]["self_hosted"]
        self.assertEqual(provider["client_type"], "public")
        self.assertEqual(provider["client_id"], oidc["client_id"])
        self.assertEqual(set(provider["grant_types"]), {"authorization_code", "refresh_token"})
        self.assertEqual(provider["redirect_uris"], [{
            "url": self.config["dashboard"]["public_url"] + "/auth/callback", "matching_mode": "strict"}])
        self.assertIn("signing_key", provider)
        scopes = {m["find"][1][1] for m in provider["property_mappings"]}
        self.assertEqual(scopes, set(oidc["scopes"].split()))

    def test_authentik_application_is_bound_only_to_owner(self):
        application = self.entry("authentik_core.application")
        self.assertEqual(application["attrs"]["slug"], "hermes")
        self.assertEqual(application["attrs"]["policy_engine_mode"], "all")
        bindings = [e for e in self.blueprint["entries"] if e["model"] == "authentik_policies.policybinding"]
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["identifiers"]["target"], {"key": application["id"]})
        self.assertEqual(bindings[0]["identifiers"]["user"],
                         {"find": ["authentik_core.user", ["username", "sveatlo"]]})
        self.assertTrue(bindings[0]["attrs"]["enabled"])

    def test_authentik_worker_mounts_the_blueprint(self):
        kustomization = yaml.safe_load((self.authentik / "kustomization.yaml").read_text())
        values = yaml.safe_load((self.authentik / "values.yaml").read_text())
        self.assertIn("config/blueprint-hermes.yaml", kustomization["resources"])
        self.assertIn("authentik-blueprint-hermes", values["blueprints"]["configMaps"])


if __name__ == "__main__":
    unittest.main()
