import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("hermes_smoke", Path(__file__).parent / "base/smoke_test.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeTests(unittest.TestCase):
    def result(self, text="SAMWISE_READY", exit_code=0, returncode=0):
        return subprocess.CompletedProcess([], returncode, json.dumps({
            "type": "result", "text": text, "exit_code": exit_code,
        }), "")

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
