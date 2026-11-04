from pathlib import Path
import subprocess
import unittest

import yaml

from test_dashboard import BlueprintLoader


ROOT = Path(__file__).parent


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = list(yaml.safe_load_all(subprocess.check_output(
            ["kubectl", "kustomize", str(ROOT)], text=True)))
        cls.pod = next(r for r in cls.resources if r["kind"] == "Deployment")["spec"]["template"]["spec"]
        cls.config = yaml.safe_load((ROOT / "instances/samwise/config.yaml").read_text())
        cm = yaml.safe_load((ROOT.parent.parent / "authentik/config/blueprint-hermes-samwise.yaml").read_text())
        cls.blueprint = yaml.load(cm["data"]["hermes-samwise.yaml"], Loader=BlueprintLoader)

    def test_browser_starts_nonroot_before_gateway_with_separate_state(self):
        sidecar = next(c for c in self.pod["initContainers"] if c["name"] == "camofox")
        self.assertEqual(sidecar["restartPolicy"], "Always")
        self.assertIn(":1.18.1@sha256:", sidecar["image"])
        self.assertEqual(sidecar["command"][0], "node")
        self.assertTrue(sidecar["securityContext"]["runAsNonRoot"])
        self.assertTrue(sidecar["securityContext"]["readOnlyRootFilesystem"])
        self.assertNotIn("envFrom", sidecar)
        env = {e["name"]: e["value"] for e in sidecar["env"]}
        self.assertEqual(env["CAMOFOX_BIND_HOST"], "127.0.0.1")
        self.assertEqual(env["VNC_RFB_BIND"], "127.0.0.1")
        self.assertEqual(env["CAMOFOX_PROFILE_DIR"], "/data/profiles")
        self.assertEqual(env["CAMOFOX_CRASH_REPORT_ENABLED"], "false")
        self.assertEqual({v["name"] for v in sidecar["volumeMounts"]}, {
            "browser-data", "browser-binary", "browser-tmp", "browser-shm",
        })
        volumes = {v["name"]: v for v in self.pod["volumes"]}
        self.assertEqual(volumes["browser-data"]["persistentVolumeClaim"]["claimName"], "hermes-browser-samwise")
        self.assertGreaterEqual(self.pod["terminationGracePeriodSeconds"], 60)
        gateway = self.pod["containers"][0]
        self.assertNotIn("browser-data", {v["name"] for v in gateway["volumeMounts"]})
        self.assertIn({"name": "CAMOFOX_URL", "value": "http://127.0.0.1:9377"}, gateway["env"])
        services = [r for r in self.resources if r["kind"] == "Service"]
        self.assertEqual({p["port"] for s in services for p in s["spec"]["ports"]}, {9119, 6080})
        self.assertTrue(all(s["spec"].get("type", "ClusterIP") == "ClusterIP" for s in services))

    def test_persistent_browser_tools_enabled_for_all_channels(self):
        self.assertIn("camofox", self.config["plugins"]["enabled"])
        self.assertIs(self.config["browser"]["camofox"]["managed_persistence"], True)
        for channel in ("telegram", "cli", "api_server"):
            self.assertIn("camofox", self.config["platform_toolsets"][channel])

    def test_lan_and_sso_cover_desktop_and_websocket_routes(self):
        route = next(r for r in self.resources if r["kind"] == "IngressRoute")
        self.assertEqual(route["spec"]["entryPoints"], ["websecure"])
        self.assertIn("tls", route["spec"])
        callback, browser = route["spec"]["routes"]
        host = "Host(`samwise-browser.${DOMAIN_0}`)"
        self.assertEqual(browser["match"], host)
        self.assertEqual(callback["match"], host + " && PathPrefix(`/outpost.goauthentik.io/`)")
        self.assertGreater(callback["priority"], browser["priority"])
        lan = {"name": "lan-only", "namespace": "traefik"}
        self.assertEqual(callback["middlewares"], [lan])
        self.assertEqual(callback["services"], [{"name": "authentik-server", "namespace": "authentik", "port": 80}])
        middleware = next(r for r in self.resources if r["kind"] == "Middleware")
        self.assertEqual(browser["middlewares"], [lan, {"name": middleware["metadata"]["name"]}])
        self.assertEqual(middleware["spec"]["forwardAuth"]["address"],
                         "http://authentik-server.authentik.svc.cluster.local/outpost.goauthentik.io/auth/traefik")
        service = next(r for r in self.resources if r["kind"] == "Service" and r["metadata"]["name"] == "hermes-browser-samwise")
        self.assertEqual(browser["services"], [{"name": service["metadata"]["name"], "port": "novnc"}])

    def test_single_app_provider_reuses_samwise_group_and_embedded_outpost(self):
        entries = self.blueprint["entries"]
        provider = next(e for e in entries if e["model"] == "authentik_providers_proxy.proxyprovider")
        self.assertEqual(provider["attrs"]["mode"], "forward_single")
        self.assertEqual(provider["attrs"]["external_host"], "https://samwise-browser.${DOMAIN_0}")
        ids = {e["id"] for e in entries if "id" in e}
        self.assertTrue(ids)
        self.assertTrue(all(local_id.startswith("hermes-samwise-") for local_id in ids))
        pending = [entries]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if set(value) == {"key"}:
                    self.assertIn(value["key"], ids)
                else:
                    pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        app = next(e for e in entries if e.get("id") == "hermes-samwise-browser-application")
        self.assertEqual(app["attrs"]["provider"], {"key": provider["id"]})
        bindings = [e for e in entries if e["model"] == "authentik_policies.policybinding"
                    and e["identifiers"]["target"] == {"key": app["id"]}]
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["identifiers"]["group"], {"key": "hermes-samwise-access"})
        self.assertTrue(bindings[0]["attrs"]["enabled"])
        outpost = next(e for e in entries if e["model"] == "authentik_outposts.outpost")
        self.assertEqual(outpost["identifiers"], {"managed": "goauthentik.io/outposts/embedded"})
        self.assertEqual(outpost["attrs"]["providers"], [{"key": provider["id"]}])


if __name__ == "__main__":
    unittest.main()
