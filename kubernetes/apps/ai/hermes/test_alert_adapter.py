import copy
from contextlib import closing
import http.client
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("adapter", Path(__file__).with_name("alert_adapter.py"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        adapter.ROOT = Path(self.tmp.name)
        for name in ("pending", "results"):
            (adapter.ROOT / name).mkdir()
        self.payload = {"groupKey": "namespace=ai", "alerts": [
            {"fingerprint": "abc", "status": "firing", "startsAt": "2026-01-01T00:00:00Z"}]}

    def pending(self):
        return list((adapter.ROOT / "pending").glob("*.json"))

    def test_retry_deduplicates_changing_end_time(self):
        adapter.enqueue(self.payload)
        self.payload["alerts"][0]["endsAt"] = "later"
        adapter.enqueue(self.payload)
        self.assertEqual(len(self.pending()), 1)

    def test_invalid_payload_rejected(self):
        for payload in (None, {}, {"groupKey": "x", "alerts": []},
                        {"groupKey": "x", "alerts": [{"fingerprint": []}]}):
            with self.assertRaises(ValueError):
                adapter.enqueue(payload)

    def test_full_queue_backpressure(self):
        for i in range(100):
            payload = copy.deepcopy(self.payload)
            payload["groupKey"] = str(i)
            self.assertTrue(adapter.enqueue(payload))
        self.assertFalse(adapter.enqueue(self.payload))

    def test_delivery_retry_does_not_rerun_model(self):
        adapter.enqueue(self.payload)
        path = self.pending()[0]
        with patch.object(adapter, "investigate", return_value={"text": "report"}) as run:
            with patch.object(adapter, "deliver", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    adapter.process(path)
            with patch.object(adapter, "deliver"):
                adapter.process(path)
            run.assert_called_once()
        self.assertFalse(self.pending())
        adapter.enqueue(self.payload)
        self.assertFalse(self.pending())

    def test_partial_delivery_retry_resumes_after_acknowledged_chunk(self):
        adapter.enqueue(self.payload)
        path = self.pending()[0]
        delivered = []
        calls = 0

        def send(request, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second chunk failed")
            delivered.append(json.loads(request.data)["text"])
            response = Mock()
            response.read.return_value = b'{"ok":true}'
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test", "TELEGRAM_HOME_CHANNEL": "123"}), \
                patch.object(adapter, "urlopen", side_effect=send), \
                patch.object(adapter, "investigate", return_value={"text": "A" * 6000 + "B"}) as run:
            with self.assertRaisesRegex(RuntimeError, "second chunk failed"):
                adapter.process(path)
            adapter.process(path)
            run.assert_called_once()
        self.assertEqual(len(delivered), 3)
        self.assertEqual("".join(delivered),
                         f"Cubie incident {path.stem[:12]}\nReport: {adapter.ROOT / 'results' / path.name}\n\n"
                         + "A" * 6000 + "B")
        self.assertFalse(self.pending())

    def test_model_failure_pauses_queue(self):
        adapter.enqueue(self.payload)
        with patch.object(adapter, "investigate", side_effect=RuntimeError), patch.object(adapter, "deliver"):
            adapter.process(self.pending()[0])
        self.assertTrue((adapter.ROOT / "PAUSED").exists())

    def test_restart_never_reexecutes_uncertain_run(self):
        adapter.enqueue(self.payload)
        path = self.pending()[0]
        adapter.save(path, {"payload": self.payload, "running": True})
        with patch.object(adapter, "investigate") as run, patch.object(adapter, "deliver"):
            adapter.process(path)
            run.assert_not_called()
        self.assertTrue((adapter.ROOT / "PAUSED").exists())

    def test_recovery_precedes_new_events_after_restart(self):
        adapter.enqueue(self.payload)
        old = self.pending()[0]
        adapter.save(old, {"payload": self.payload, "running": True})
        new = copy.deepcopy(self.payload)
        new["groupKey"] = "other"
        adapter.enqueue(new)
        os.utime(old, (2000000000, 2000000000))
        with patch.object(adapter, "process") as process, patch.object(adapter.time, "sleep", side_effect=RuntimeError("stop")):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                adapter.worker()
            process.assert_called_once_with(old)

    def test_http_auth_payload_limits_and_health(self):
        server = adapter.Server(("127.0.0.1", 0), adapter.Handler)
        server.worker = Mock()
        server.worker.is_alive.return_value = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with patch.dict(os.environ, {"ALERT_WEBHOOK_TOKEN": "test-token"}):
            for token, body, status in (
                ("wrong", self.payload, 401),
                ("test-token", {}, 400),
                ("test-token", self.payload, 202),
                ("test-token", "x" * 65536, 413),
            ):
                with closing(http.client.HTTPConnection("127.0.0.1", server.server_port)) as client:
                    client.request("POST", "/alerts", json.dumps(body), {"Authorization": "Bearer " + token})
                    self.assertEqual(client.getresponse().status, status)
            for alive, status in ((True, 200), (False, 503)):
                server.worker.is_alive.return_value = alive
                with closing(http.client.HTTPConnection("127.0.0.1", server.server_port)) as client:
                    client.request("GET", "/health")
                    self.assertEqual(client.getresponse().status, status)


if __name__ == "__main__":
    unittest.main()
