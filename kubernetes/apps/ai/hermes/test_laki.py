import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

import yaml


ROOT = Path(__file__).parent
LAKI = ROOT / "instances/laki"


def render(path):
    return list(yaml.safe_load_all(subprocess.check_output(
        ["kubectl", "kustomize", str(path)], text=True,
    )))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, LAKI / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LakiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = render(ROOT)
        cls.laki = [r for r in cls.resources
                    if r["metadata"].get("labels", {}).get("app.kubernetes.io/instance") == "hermes-laki"]
        cls.deployment = next(r for r in cls.laki if r["kind"] == "Deployment")
        cls.pod = cls.deployment["spec"]["template"]["spec"]
        cls.gateway = next(c for c in cls.pod["containers"] if c["name"] == "gateway")
        cls.cm = next(r for r in cls.laki if r["kind"] == "ConfigMap")
        cls.config = yaml.safe_load(cls.cm["data"]["config.yaml"])

    def test_config_sources_are_not_git_ignored(self):
        overlay = yaml.safe_load((LAKI / "kustomization.yaml").read_text())
        for generator in overlay["configMapGenerator"]:
            for entry in generator.get("files", []):
                source = LAKI / entry.split("=", 1)[-1]
                result = subprocess.run(
                    ["git", "check-ignore", "--no-index", "--quiet", str(source)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 1, f"Config source is ignored or cannot be checked: {source}")

    def test_active_shared_image_and_fresh_isolated_storage(self):
        self.assertEqual(self.deployment["spec"]["replicas"], 1)
        samwise = next(r for r in self.resources if r["kind"] == "Deployment"
                       and r["metadata"]["name"] == "hermes-samwise")
        self.assertEqual(self.gateway["image"], samwise["spec"]["template"]["spec"]["containers"][0]["image"])
        operator_init = next(c for c in self.pod["initContainers"] if c["name"] == "operator-configure")
        self.assertEqual(operator_init["image"], self.gateway["image"])
        self.assertRegex(self.gateway["image"], r"^docker\.io/nousresearch/hermes-agent:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")
        for instance in ("samwise", "laki"):
            deployment = next(r for r in self.resources if r["kind"] == "Deployment"
                              and r["metadata"]["name"] == f"hermes-{instance}")
            pod = deployment["spec"]["template"]["spec"]
            selector = deployment["spec"]["selector"]["matchLabels"]
            self.assertEqual(selector["app.kubernetes.io/instance"], f"hermes-{instance}")
            self.assertEqual(deployment["spec"]["template"]["metadata"]["labels"], selector)
            volumes = {v["name"]: v for v in pod["volumes"]}
            self.assertEqual(volumes["data"]["persistentVolumeClaim"]["claimName"], f"hermes-{instance}")
            self.assertEqual(volumes["browser-data"]["persistentVolumeClaim"]["claimName"], f"hermes-{instance}-browser")
            cm = next(r for r in self.resources if r["kind"] == "ConfigMap"
                      and r["metadata"]["labels"]["app.kubernetes.io/instance"] == f"hermes-{instance}")
            self.assertEqual(volumes["config"]["configMap"]["name"], cm["metadata"]["name"])
            for service in [r for r in self.resources if r["kind"] == "Service"
                            and r["metadata"]["labels"]["app.kubernetes.io/instance"] == f"hermes-{instance}"]:
                self.assertEqual(service["spec"]["selector"], selector)
        for resource in self.laki:
            self.assertTrue(resource["metadata"]["name"].startswith("hermes-laki"))
        self.assertEqual({r["metadata"]["name"] for r in self.laki if r["kind"] == "PersistentVolumeClaim"},
                         {"hermes-laki", "hermes-laki-browser"})
        self.assertFalse(any(r["kind"] == "Secret" for r in self.laki))

    def test_samwise_combined_output_matches_its_standalone_overlay(self):
        standalone = render(ROOT / "instances/samwise")
        combined = {(r["kind"], r["metadata"]["name"]): r for r in self.resources
                    if r["metadata"].get("labels", {}).get("app.kubernetes.io/instance") == "hermes-samwise"}
        self.assertEqual(len(standalone), len(combined))
        for resource in standalone:
            resource["metadata"]["namespace"] = "ai"
            self.assertEqual(resource, combined[(resource["kind"], resource["metadata"]["name"])])

    def test_no_external_api_or_unrequested_integrations(self):
        self.assertEqual({r["metadata"]["name"] for r in self.laki if r["kind"] == "Service"},
                         {"hermes-laki-dashboard", "hermes-laki-browser"})
        env = {e["name"]: e for e in self.gateway["env"]}
        self.assertEqual(env["API_SERVER_ENABLED"]["value"], "false")
        self.assertEqual({key for key in env if key.startswith("API_SERVER_")}, {"API_SERVER_ENABLED"})
        self.assertEqual(self.gateway["ports"], [{"name": "dashboard", "containerPort": 9119}])
        self.assertNotIn("hermes-api", yaml.safe_dump(self.laki))
        self.assertEqual(self.config["plugins"]["enabled"], ["homeassistant", "camofox"])
        self.assertEqual(set(self.config["mcp_servers"]), {"kraken"})
        self.assertEqual(set(self.config["platform_toolsets"]), {"telegram", "cli"})
        self.assertFalse(self.config["platforms"]["homeassistant"]["enabled"])
        self.assertEqual(set(self.config["platforms"]), {"homeassistant"})
        self.assertEqual({c["name"] for c in self.pod["initContainers"]},
                         {"browser-binary", "camofox", "configure", "operator-configure"})
        self.assertEqual([c["name"] for c in self.pod["containers"]], ["gateway"])

    def test_smart_approvals_and_owner_only_default(self):
        self.assertEqual(self.config["approvals"], {
            "mode": "smart", "unattended_mode": "deny", "single_query_mode": "deny", "cron_mode": "deny",
        })
        self.assertEqual(self.config["gateway"], {"allow_all_users": False, "unauthorized_dm_behavior": "ignore"})
        env = {e["name"]: e for e in self.gateway["env"]}
        self.assertEqual(env["GATEWAY_ALLOW_ALL_USERS"]["value"], "false")
        self.assertIn("cronjob", self.config["platform_toolsets"]["telegram"])
        self.assertEqual(self.config["model"], yaml.safe_load((ROOT / "instances/samwise/config.yaml").read_text())["model"])
        soul = self.cm["data"]["SOUL.md"]
        for boundary in ("confirmation boundary", "Never merge", "Never SSH", "camera imagery", "raw household-history store"):
            self.assertIn(boundary, soul)
        self.assertIn("read-only and suggestions-only", self.cm["data"]["daily-review.md"])

    def test_operator_token_and_talos_mounts_only_reach_gateway(self):
        self.assertEqual(self.pod["serviceAccountName"], "hermes-laki")
        self.assertFalse(self.pod["automountServiceAccountToken"])
        binding = next(r for r in self.laki if r["kind"] == "ClusterRoleBinding")
        self.assertEqual(binding["roleRef"]["name"], "cluster-admin")
        self.assertEqual(binding["subjects"], [{"kind": "ServiceAccount", "name": "hermes-laki", "namespace": "ai"}])
        volumes = {v["name"]: v for v in self.pod["volumes"]}
        self.assertEqual(volumes["kube-api"]["projected"]["sources"][0], {
            "serviceAccountToken": {"path": "token", "expirationSeconds": 3600},
        })
        kubeconfig = yaml.safe_load(self.cm["data"]["kubeconfig"])
        self.assertEqual(kubeconfig["users"][0]["user"], {
            "tokenFile": "/var/run/secrets/kubernetes.io/serviceaccount/token",
        })
        for container in self.pod["containers"] + self.pod["initContainers"]:
            mounts = {m["name"] for m in container.get("volumeMounts", [])}
            self.assertEqual("kube-api" in mounts, container["name"] == "gateway")
            self.assertEqual("talos" in mounts, container["name"] == "gateway")
        self.assertEqual(volumes["talos"]["secret"]["secretName"], "hermes-laki-talos")
        self.assertTrue(volumes["talos"]["secret"]["optional"])
        self.assertEqual(volumes["managed-env"]["projected"]["sources"], [
            {"secret": {"name": "hermes-laki-credentials"}},
            {"secret": {"name": "hermes-laki-homeassistant"}},
            {"secret": {"name": "hermes-laki-operator"}},
            {"secret": {"name": "hermes-laki-kraken", "optional": True}},
        ])
        for name in ("homeassistant", "operator"):
            self.assertIn({"prefix": "_HERMES_FORCE_", "secretRef": {"name": f"hermes-laki-{name}"}},
                          self.gateway["envFrom"])

    def test_dashboard_and_browser_have_lan_and_laki_auth_routing(self):
        ingress = next(r for r in self.laki if r["kind"] == "Ingress")
        self.assertEqual(ingress["metadata"]["annotations"]["traefik.ingress.kubernetes.io/router.middlewares"],
                         "traefik-lan-only@kubernetescrd")
        self.assertEqual(ingress["spec"]["rules"][0]["host"], "laki.${DOMAIN_0}")
        self.assertEqual(ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"],
                         "hermes-laki-dashboard")
        self.assertEqual(self.config["dashboard"]["oauth"]["self_hosted"]["client_id"], "hermes-laki-dashboard")
        routes = next(r for r in self.laki if r["kind"] == "IngressRoute")["spec"]["routes"]
        for route in routes:
            self.assertIn("laki-browser.${DOMAIN_0}", route["match"])
            self.assertIn({"name": "lan-only", "namespace": "traefik"}, route["middlewares"])
        self.assertIn({"name": "hermes-laki-browser-auth"}, routes[1]["middlewares"])
        self.assertEqual(routes[1]["services"][0]["name"], "hermes-laki-browser")
        self.assertTrue(self.config["browser"]["camofox"]["managed_persistence"])

    def test_git_helper_never_returns_credentials_for_other_hosts(self):
        helper = load_script("git-credential")
        self.assertEqual(helper.credential({"protocol": "https", "host": "github.com"}, "test-token"),
                         "username=x-access-token\npassword=test-token\n\n")
        for protocol, host in (("http", "github.com"), ("https", "git.github.com"),
                               ("https", "github.com.attacker.invalid"), ("https", "gitea")):
            self.assertEqual(helper.credential({"protocol": protocol, "host": host}, "test-token"), "")
        self.assertEqual(helper.credential({"protocol": "https", "host": "github.com"}, ""), "")

    def test_tool_download_is_checksum_checked_before_replacing_binary(self):
        initializer = load_script("operator-init")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            binary = b"verified test binary"
            digest = hashlib.sha256(binary).hexdigest()
            fetch = Mock(side_effect=lambda *args, **kwargs: io.BytesIO(binary))
            tools = [("kubectl", "https://example.invalid/kubectl", digest)]
            initializer.install_tools(path, tools, fetch)
            self.assertEqual((path / "kubectl").read_bytes(), binary)
            self.assertEqual((path / "kubectl").stat().st_mode & 0o777, 0o755)
            initializer.install_tools(path, tools, fetch)
            self.assertEqual(fetch.call_count, 1)
            tools = [("kubectl", "https://example.invalid/kubectl", "0" * 64)]
            with self.assertRaisesRegex(RuntimeError, "Checksum mismatch: kubectl"):
                initializer.install_tools(path, tools, fetch)
            self.assertEqual((path / "kubectl").read_bytes(), binary)


if __name__ == "__main__":
    unittest.main()
