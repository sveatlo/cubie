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

    def test_staged_instance_has_one_gateway_and_no_operator_permissions(self):
        deployments = [r for r in self.resources if r["kind"] == "Deployment"]
        self.assertEqual([d["metadata"]["name"] for d in deployments], ["hermes-samwise"])
        deployment = deployments[0]
        self.assertEqual(deployment["spec"]["replicas"], 0)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertFalse(pod["enableServiceLinks"])
        self.assertNotIn("serviceAccountName", pod)
        self.assertEqual([c["name"] for c in pod["containers"]], ["gateway"])
        self.assertFalse(any(r["kind"] in ("ClusterRoleBinding", "RoleBinding", "ServiceAccount") for r in self.resources))
        self.assertEqual({v["name"] for v in pod["volumes"]}, {"data", "config"})
        gateway = pod["containers"][0]
        self.assertNotIn("command", gateway)
        self.assertEqual(gateway["args"], ["gateway", "run"])
        self.assertEqual(gateway["envFrom"][0], {"secretRef": {"name": "hermes-credentials-samwise"}})
        env = {e["name"]: e.get("value") for e in gateway["env"]}
        self.assertEqual(env["HERMES_DASHBOARD"], "true")
        self.assertEqual(env["HERMES_DASHBOARD_HOST"], "0.0.0.0")
        self.assertNotIn("HERMES_DASHBOARD_INSECURE", env)
        self.assertFalse(any("GITHUB" in key or "TALOS" in key or "PROXMOX" in key for key in env))
        for name in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertGreater(gateway[name]["timeoutSeconds"], 2)

    def test_only_fresh_instance_storage_is_managed_and_mounted(self):
        claims = {r["metadata"]["name"]: r for r in self.resources if r["kind"] == "PersistentVolumeClaim"}
        self.assertEqual(set(claims), {"hermes-samwise"})
        pod = next(r for r in self.resources if r["kind"] == "Deployment")["spec"]["template"]["spec"]
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], "hermes-samwise")
        self.assertFalse(any(r["kind"] == "Pod" for r in self.resources))
        self.assertFalse(any(v.get("persistentVolumeClaim", {}).get("claimName") == "hermes" for v in pod["volumes"]))

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
            for name in ("kustomization.yaml", "config.yaml", "ingress.yaml"):
                path = second / name
                path.write_text(path.read_text().replace("samwise", "test-other"))
            other = render(second)
        original = [r for r in self.resources if r["metadata"]["name"] != "hermes"]
        self.assertTrue({(r["kind"], r["metadata"]["name"]) for r in original}.isdisjoint(
            {(r["kind"], r["metadata"]["name"]) for r in other}))
        for resources, instance in ((original, "samwise"), (other, "test-other")):
            deployment = next(r for r in resources if r["kind"] == "Deployment")
            selector = deployment["spec"]["selector"]["matchLabels"]
            self.assertEqual(selector["app.kubernetes.io/instance"], instance)
            self.assertEqual(deployment["spec"]["template"]["metadata"]["labels"], selector)
            service = next(r for r in resources if r["kind"] == "Service")
            self.assertEqual(service["spec"]["selector"], selector)
            volumes = deployment["spec"]["template"]["spec"]["volumes"]
            self.assertEqual(volumes[0]["persistentVolumeClaim"]["claimName"], "hermes-" + instance)

    def test_alertmanager_keeps_email_without_hermes_receiver(self):
        values = yaml.safe_load((ROOT.parents[2] / "infrastructure/kube-prometheus-stack/values.yaml").read_text())
        config = yaml.safe_load(values["alertmanager"]["stringConfig"])
        self.assertEqual(config["route"]["receiver"], "default")
        self.assertEqual([r["name"] for r in config["receivers"]], ["default"])
        self.assertNotIn("hermes-alert-webhook", values["alertmanager"]["alertmanagerSpec"]["secrets"])
        self.assertTrue(config["receivers"][0]["email_configs"])


if __name__ == "__main__":
    unittest.main()
