from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).parent


def render(path):
    return list(yaml.safe_load_all(subprocess.check_output(["kubectl", "kustomize", str(path)], text=True)))


class InstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = render(ROOT)

    def test_active_instance_has_one_gateway_and_no_operator_permissions(self):
        deployments = [r for r in self.resources if r["kind"] == "Deployment"]
        self.assertEqual([d["metadata"]["name"] for d in deployments], ["hermes-samwise"])
        deployment = deployments[0]
        self.assertEqual(deployment["spec"]["replicas"], 1)
        base = render(ROOT / "base")
        self.assertEqual(next(r for r in base if r["kind"] == "Deployment")["spec"]["replicas"], 0)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertFalse(pod["enableServiceLinks"])
        self.assertNotIn("serviceAccountName", pod)
        self.assertEqual([c["name"] for c in pod["containers"]], ["gateway"])
        self.assertFalse(any(r["kind"] in ("ClusterRoleBinding", "RoleBinding", "ServiceAccount") for r in self.resources))
        self.assertEqual({v["name"] for v in pod["volumes"]}, {"data", "config", "mealie-tmp", "browser-binary", "browser-data", "browser-tmp", "browser-shm"})
        gateway = pod["containers"][0]
        self.assertNotIn("command", gateway)
        self.assertEqual(gateway["args"], ["gateway", "run"])
        self.assertEqual(gateway["envFrom"][0], {"secretRef": {"name": "hermes-samwise-credentials"}})
        env = {e["name"]: e.get("value") for e in gateway["env"]}
        self.assertEqual(env["HERMES_DASHBOARD"], "true")
        self.assertEqual(env["HERMES_DASHBOARD_HOST"], "0.0.0.0")
        self.assertNotIn("HERMES_DASHBOARD_INSECURE", env)
        self.assertFalse(any("GITHUB" in key or "TALOS" in key or "PROXMOX" in key for key in env))
        for name in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertGreater(gateway[name]["timeoutSeconds"], 2)

    def test_mealie_starts_before_gateway_and_is_private_to_the_instance(self):
        deployment = next(r for r in self.resources if r["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        sidecar = next(c for c in pod["initContainers"] if c["name"] == "mealie-mcp")
        self.assertEqual(sidecar["restartPolicy"], "Always")
        self.assertIn("startupProbe", sidecar)
        self.assertIn("@sha256:", sidecar["image"])
        self.assertEqual(sidecar["args"], ["--http", "8000"])
        env = {e["name"]: e for e in sidecar["env"]}
        self.assertEqual(env["MCP_HOST"]["value"], "127.0.0.1")
        self.assertEqual(env["MEALIE_BASE_URL"]["value"], "http://mealie.mealie.svc.cluster.local:9000")
        self.assertEqual(env["MEALIE_API_TOKEN"]["valueFrom"]["secretKeyRef"], {
            "name": "hermes-samwise-mealie", "key": "MEALIE_API_TOKEN",
        })
        self.assertTrue(sidecar["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual([v["name"] for v in sidecar["volumeMounts"]], ["mealie-tmp"])
        self.assertNotIn("MEALIE_INCLUDE_TAGS", env)
        self.assertNotIn("MEALIE_EXCLUDE_TAGS", env)
        base = next(r for r in render(ROOT / "base") if r["kind"] == "Deployment")
        self.assertEqual([c["name"] for c in base["spec"]["template"]["spec"]["initContainers"]], ["browser-binary", "camofox", "configure"])
        for resource in self.resources:
            if resource["kind"] == "Service" and resource["metadata"]["name"] == "hermes-samwise-dashboard":
                self.assertEqual([p["port"] for p in resource["spec"]["ports"]], [9119])
        config = yaml.safe_load(next(r for r in self.resources if r["kind"] == "ConfigMap")["data"]["config.yaml"])
        self.assertEqual(config["mcp_servers"]["mealie"], {"url": "http://127.0.0.1:8000/mcp"})
        for platform in ("telegram", "cli", "api_server"):
            self.assertIn("mcp-mealie", config["platform_toolsets"][platform])

    def test_only_fresh_instance_storage_is_managed_and_mounted(self):
        claims = {r["metadata"]["name"]: r for r in self.resources if r["kind"] == "PersistentVolumeClaim"}
        self.assertEqual(set(claims), {"hermes-samwise", "hermes-samwise-browser"})
        pod = next(r for r in self.resources if r["kind"] == "Deployment")["spec"]["template"]["spec"]
        self.assertEqual(next(v for v in pod["volumes"] if v["name"] == "data")["persistentVolumeClaim"]["claimName"], "hermes-samwise")
        self.assertFalse(any(r["kind"] == "Pod" for r in self.resources))
        self.assertFalse(any(v.get("persistentVolumeClaim", {}).get("claimName") == "hermes" for v in pod["volumes"]))

    def test_internal_names_share_the_instance_prefix(self):
        for resource in self.resources:
            self.assertTrue(resource["metadata"]["name"].startswith("hermes-samwise"))
            self.assertEqual(resource["metadata"]["labels"]["app.kubernetes.io/instance"], "hermes-samwise")
        config = next(r for r in self.resources if r["kind"] == "ConfigMap")
        self.assertTrue(config["metadata"]["name"].startswith("hermes-samwise-config-"))
        deployment = next(r for r in self.resources if r["kind"] == "Deployment")
        volumes = deployment["spec"]["template"]["spec"]["volumes"]
        self.assertEqual(next(v for v in volumes if v["name"] == "config")["configMap"]["name"], config["metadata"]["name"])
        for component in ("credentials", "homeassistant", "mealie"):
            self.assertTrue((ROOT.parent / "config" / f"hermes-samwise-{component}.yaml.sops").exists())

    def test_generated_config_contains_only_household_runtime(self):
        cm = next(r for r in self.resources if r["kind"] == "ConfigMap")
        self.assertEqual(set(cm["data"]), {"init.py", "smoke_test.py", "config.yaml", "SOUL.md"})
        self.assertIn("Samwise Gamgee", cm["data"]["SOUL.md"])
        self.assertIn("everyone who has access", cm["data"]["SOUL.md"])
        for metadata in ("Rohlík", "sveatlo", "Sväťo", "OpenAI", "subscription", "homelab", "administrator access"):
            self.assertNotIn(metadata, cm["data"]["SOUL.md"])

    def test_second_overlay_has_disjoint_resources_selectors_and_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "hermes"
            shutil.copytree(ROOT, copy)
            second = copy / "instances/test-other"
            shutil.copytree(copy / "instances/samwise", second)
            for name in ("kustomization.yaml", "config.yaml", "ingress.yaml", "browser-ingress.yaml", "mealie-mcp.yaml"):
                path = second / name
                path.write_text(path.read_text().replace("samwise", "test-other"))
            other = render(second)
        original = [r for r in self.resources if r["metadata"]["name"] != "hermes"]
        self.assertTrue({(r["kind"], r["metadata"]["name"]) for r in original}.isdisjoint(
            {(r["kind"], r["metadata"]["name"]) for r in other}))
        for resources, instance in ((original, "samwise"), (other, "test-other")):
            deployment = next(r for r in resources if r["kind"] == "Deployment")
            selector = deployment["spec"]["selector"]["matchLabels"]
            self.assertEqual(selector["app.kubernetes.io/instance"], "hermes-" + instance)
            self.assertEqual(deployment["spec"]["template"]["metadata"]["labels"], selector)
            service = next(r for r in resources if r["kind"] == "Service")
            self.assertEqual(service["spec"]["selector"], selector)
            volumes = deployment["spec"]["template"]["spec"]["volumes"]
            self.assertEqual(next(v for v in volumes if v["name"] == "data")["persistentVolumeClaim"]["claimName"], "hermes-" + instance)
            self.assertEqual(next(v for v in volumes if v["name"] == "browser-data")["persistentVolumeClaim"]["claimName"], "hermes-" + instance + "-browser")
            browser_route = next(r for r in resources if r["kind"] == "IngressRoute")
            self.assertEqual(browser_route["spec"]["routes"][1]["services"][0]["name"], "hermes-" + instance + "-browser")
            self.assertEqual(browser_route["spec"]["routes"][1]["middlewares"][1]["name"], "hermes-" + instance + "-browser-auth")
            mealie = next(c for c in deployment["spec"]["template"]["spec"]["initContainers"] if c["name"] == "mealie-mcp")
            token = next(e for e in mealie["env"] if e["name"] == "MEALIE_API_TOKEN")
            self.assertEqual(token["valueFrom"]["secretKeyRef"]["name"], "hermes-" + instance + "-mealie")

    def test_alertmanager_keeps_email_without_hermes_receiver(self):
        values = yaml.safe_load((ROOT.parents[2] / "infrastructure/kube-prometheus-stack/values.yaml").read_text())
        config = yaml.safe_load(values["alertmanager"]["stringConfig"])
        self.assertEqual(config["route"]["receiver"], "default")
        self.assertEqual([r["name"] for r in config["receivers"]], ["default"])
        self.assertNotIn("hermes-alert-webhook", values["alertmanager"]["alertmanagerSpec"]["secrets"])
        self.assertTrue(config["receivers"][0]["email_configs"])


if __name__ == "__main__":
    unittest.main()
