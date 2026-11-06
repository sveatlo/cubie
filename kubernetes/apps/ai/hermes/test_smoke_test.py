import copy
import importlib.util
import io
import json
from pathlib import Path
import runpy
import subprocess
import traceback
import unittest
from unittest.mock import call, patch
from urllib.error import HTTPError


spec = importlib.util.spec_from_file_location("hermes_smoke", Path(__file__).parent / "base/smoke_test.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeTests(unittest.TestCase):
    def result(self, text="SAMWISE_READY", exit_code=0, returncode=0):
        return subprocess.CompletedProcess([], returncode, json.dumps({
            "type": "result", "text": text, "exit_code": exit_code,
        }), "")

    def capabilities(self):
        return {
            "auth": {"type": "bearer", "required": True},
            "features": {
                "run_submission": True, "run_status": True, "run_stop": True,
                "run_approval_response": True, "run_unknown_resolution": True,
                "session_resources": True,
                "runs_idempotency": {"supported": True, "durable": True, "retention_seconds": 86400},
            },
        }

    def test_api_only_reads_authenticated_and_unauthenticated_capabilities(self):
        error = HTTPError("http://localhost", 401, "Unauthorized", {}, io.BytesIO(b"private"))
        with patch.dict(smoke.os.environ, {"API_SERVER_KEY": "fake-api-key"}), \
                patch.object(smoke, "request_json", side_effect=[self.capabilities(), error]) as request, \
                patch.object(smoke.subprocess, "run") as run:
            smoke.api()
        self.assertEqual(request.call_args_list, [
            call("http://127.0.0.1:8642/v1/capabilities", {"Authorization": "Bearer fake-api-key"}),
            call("http://127.0.0.1:8642/v1/capabilities"),
        ])
        self.assertTrue(error.fp.closed)
        run.assert_not_called()

    def test_api_requires_all_features_and_durable_idempotency(self):
        valid = self.capabilities()
        invalid = []
        for section, name, value in (
            ("auth", "required", False), ("auth", "type", "none"),
            *(("features", name, False) for name in valid["features"] if name != "runs_idempotency"),
        ):
            payload = copy.deepcopy(valid)
            payload[section][name] = value
            invalid.append(payload)
        for name, value in (("supported", False), ("durable", False), ("retention_seconds", 86399)):
            payload = copy.deepcopy(valid)
            payload["features"]["runs_idempotency"][name] = value
            invalid.append(payload)
        payload = copy.deepcopy(valid)
        payload["features"]["run_approval"] = payload["features"].pop("run_approval_response")
        invalid.extend([payload, {}, None])
        for payload in invalid:
            with self.subTest(payload=payload), \
                    patch.dict(smoke.os.environ, {"API_SERVER_KEY": "fake-api-key"}), \
                    patch.object(smoke, "request_json", return_value=payload) as request:
                with self.assertRaisesRegex(RuntimeError, "API authentication or capabilities check failed"):
                    smoke.api()
                request.assert_called_once()

    def test_api_rejects_unauthenticated_success_and_non_401_errors(self):
        for response in ({}, HTTPError("http://localhost", 403, "private-response", {}, None)):
            with self.subTest(response=response), \
                    patch.dict(smoke.os.environ, {"API_SERVER_KEY": "fake-api-key"}), \
                    patch.object(smoke, "request_json", side_effect=[self.capabilities(), response]):
                with self.assertRaisesRegex(RuntimeError, "API authentication or capabilities check failed"):
                    smoke.api()

    def test_api_requires_an_injected_nonempty_key(self):
        for env in ({}, {"API_SERVER_KEY": " "}):
            with self.subTest(env=env), patch.dict(smoke.os.environ, env, clear=True), \
                    patch.object(smoke, "request_json") as request:
                with self.assertRaises((KeyError, RuntimeError)):
                    smoke.api()
                request.assert_not_called()

    def test_api_cli_redacts_transport_errors(self):
        with patch.dict(smoke.os.environ, {"API_SERVER_KEY": "fake-api-key"}), \
                patch.object(smoke.sys, "argv", ["smoke_test.py", "api"]), \
                patch("urllib.request.urlopen", side_effect=RuntimeError("fake-api-key private-response")):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(str(Path(smoke.__file__)), run_name="__main__")
        message = "".join(traceback.format_exception(raised.exception))
        self.assertIn("Smoke check failed", message)
        self.assertNotIn("fake-api-key", message)
        self.assertNotIn("private-response", message)

    def test_json_requests_use_get_without_a_body(self):
        with patch.object(smoke, "urlopen") as open_url:
            open_url.return_value.__enter__.return_value = io.BytesIO(b"{}")
            self.assertEqual(smoke.request_json("http://localhost/v1/capabilities"), {})
        args, kwargs = open_url.call_args
        self.assertEqual(args[0].get_method(), "GET")
        self.assertIsNone(args[0].data)
        self.assertEqual(kwargs, {"timeout": 20})

    def test_model_uses_one_turn_without_tools_or_fallback(self):
        with patch.object(smoke.subprocess, "run", return_value=self.result()) as run:
            smoke.model()
        args, kwargs = run.call_args
        self.assertEqual(args[0], [
            "hermes", "chat", "--query-file", "-", "--oneshot", "--format", "stream-json",
            "--toolsets", "none", "--max-turns", "1", "--run-budget", "60",
        ])
        self.assertEqual(kwargs["timeout"], 90)
        self.assertTrue(kwargs["capture_output"])

    def test_failed_or_incomplete_model_responses_are_rejected(self):
        responses = [self.result(exit_code=1), self.result(returncode=1),
                     self.result(text="Something else"), subprocess.CompletedProcess([], 0, "", "")]
        for response in responses:
            with self.subTest(response=response), patch.object(smoke.subprocess, "run", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "No fallback attempted"):
                    smoke.model()

    def test_model_timeout_does_not_retry(self):
        with patch.object(smoke.subprocess, "run", side_effect=subprocess.TimeoutExpired("hermes", 90)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                smoke.model()
        run.assert_called_once()

    def test_integration_checks_only_read_telegram_identity_and_ha_root(self):
        with patch.dict(smoke.os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake-telegram-token", "HASS_URL": "https://ha.invalid/",
            "HASS_TOKEN": "fake-ha-token",
        }), patch.object(smoke, "request_json") as request:
            smoke.integrations()
        self.assertEqual(request.call_args_list[0].args, (
            "https://api.telegram.org/botfake-telegram-token/getMe",
        ))
        self.assertEqual(request.call_args_list[1].args, (
            "https://ha.invalid/api/", {"Authorization": "Bearer fake-ha-token"},
        ))
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
