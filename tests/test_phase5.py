import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONITORING_DIR = PROJECT_ROOT / "monitoring"


def _load_module(name, relpath):
    path = MONITORING_DIR / relpath
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPhase5(unittest.TestCase):
    def test_health_snapshot(self):
        api = _load_module("api", "api.py")
        fake_stdout = json.dumps({
            "overall": "HEALTHY",
            "hosts": [{
                "host": "server1",
                "timestamp": "2026-01-01T00:00:00Z",
                "overall": "HEALTHY",
                "warnings": [],
                "failed_checks": [],
                "checks": {"host": "server1"},
            }],
        })

        class FakeCompleted:
            returncode = 0
            stdout = fake_stdout
            stderr = ""

        with patch.dict(os.environ, {}, clear=True):
            with patch("subprocess.run", return_value=FakeCompleted()):
                result = api._health_snapshot("server1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["server"], "server1")
        self.assertIn("report", result)
        self.assertIn("triage", result)
        self.assertIn("host", result)

    def test_api_commands_smoke(self):
        actions = _load_module("monitoring.actions", "actions.py")
        triage = _load_module("monitoring.triage", "triage.py")
        observability = _load_module("monitoring.observability", "observability.py")
        api = _load_module("api", "api.py")

        with tempfile.TemporaryDirectory() as tmp:
            actions_path = Path(tmp) / "actions_index.json"
            health_path = Path(tmp) / "reports_index.json"
            fake_stdout = json.dumps({
                "overall": "HEALTHY",
                "hosts": [{"host": "server1", "timestamp": "2026-01-01T00:00:00Z", "overall": "HEALTHY", "warnings": [], "failed_checks": [], "checks": {"host": "server1"}}],
            })

            class FakeCompleted:
                returncode = 0
                stdout = fake_stdout
                stderr = ""

            with patch.object(actions, "ACTIONS_INDEX", actions_path), \
                 patch.object(triage, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "ACTIONS_INDEX", actions_path), \
                 patch.dict(os.environ, {}, clear=True), \
                 patch("subprocess.run", return_value=FakeCompleted()):
                allowlist = api._action_allowlist()
            self.assertTrue(allowlist["ok"])
            self.assertEqual([item["action"] for item in allowlist["actions"]], ["restart_apache", "restart_nginx", "clear_logs", "show_logs"])

            unique = "phase5-smoke"
            with patch.object(actions, "ACTIONS_INDEX", actions_path), \
                 patch.object(triage, "REPORTS_INDEX", health_path), \
                 patch("subprocess.run", return_value=FakeCompleted()):
                request = api._action_request(unique, "show_logs", "server1")
            self.assertTrue(request["ok"])
            self.assertEqual(request["request"]["status"], "pending_confirmation")

            with patch.object(actions, "ACTIONS_INDEX", actions_path):
                cancel = api._action_cancel(unique, "show_logs", "server1")
            self.assertTrue(cancel["ok"])
            self.assertEqual(cancel["result"]["status"], "cancelled")

            with patch.object(actions, "ACTIONS_INDEX", actions_path):
                audit = api._action_history(limit=5)
            self.assertTrue(audit["ok"])
            self.assertIn("audit", audit)

            with patch.object(actions, "ACTIONS_INDEX", actions_path), \
                 patch.object(triage, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "ACTIONS_INDEX", actions_path), \
                 patch("subprocess.run", return_value=FakeCompleted()):
                export_result = api._export_snapshot()
            self.assertTrue(export_result["ok"])
            self.assertIn("timestamp", export_result["snapshot"])

            with patch.object(observability, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "ACTIONS_INDEX", actions_path):
                retention_result = api._retention(keep=20)
            self.assertTrue(retention_result["ok"])
            self.assertIn("retention", retention_result)


if __name__ == "__main__":
    unittest.main()
