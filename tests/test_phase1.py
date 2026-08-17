import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONITORING_DIR = PROJECT_ROOT / "monitoring"


def _load_module(name, relpath):
    path = MONITORING_DIR / relpath
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLocalHealth(unittest.TestCase):
    def test_evaluate_healthy(self):
        local_health = _load_module("local_health", "local_health.py")
        checks = {
            "cpu_usage_percent": 10.0,
            "ram_usage_percent": 40.0,
            "disk_usage_percent": 30.0,
            "load_avg": {"1m": 0.5, "cores": 2},
            "services": {"apache2": "active", "nginx": "active", "ssh": "active"},
            "network": "reachable",
            "http_apache_8080": 200,
            "http_nginx_80": 200,
        }
        result = local_health.evaluate(checks)
        self.assertEqual(result["overall"], "HEALTHY")
        self.assertEqual(result["failed_checks"], [])
        self.assertEqual(result["warnings"], [])

    def test_evaluate_warning(self):
        local_health = _load_module("local_health", "local_health.py")
        checks = {
            "cpu_usage_percent": 85.0,
            "ram_usage_percent": 40.0,
            "disk_usage_percent": 30.0,
            "load_avg": {"1m": 0.5, "cores": 2},
            "services": {"apache2": "active", "nginx": "active", "ssh": "active"},
            "network": "reachable",
            "http_apache_8080": 200,
            "http_nginx_80": 500,
        }
        result = local_health.evaluate(checks)
        self.assertEqual(result["overall"], "WARNING")
        self.assertTrue(any("CPU usage" in msg for msg in result["warnings"]))
        self.assertTrue(any("Nginx HTTP 500" in msg for msg in result["warnings"]))

    def test_evaluate_critical(self):
        local_health = _load_module("local_health", "local_health.py")
        checks = {
            "cpu_usage_percent": 96.0,
            "ram_usage_percent": 40.0,
            "disk_usage_percent": 30.0,
            "load_avg": {"1m": 0.5, "cores": 2},
            "services": {"apache2": "inactive", "nginx": "active", "ssh": "active"},
            "network": "unreachable",
            "http_apache_8080": 200,
            "http_nginx_80": 200,
        }
        result = local_health.evaluate(checks)
        self.assertEqual(result["overall"], "CRITICAL")
        self.assertTrue(any("CPU usage" in msg for msg in result["failed_checks"]))
        self.assertTrue(any("Service apache2 is inactive" in msg for msg in result["failed_checks"]))
        self.assertTrue(any("Network connectivity is unreachable" in msg for msg in result["failed_checks"]))

    def test_main_json_structure(self):
        local_health = _load_module("local_health", "local_health.py")
        fake_checks = {
            "host": "server1",
            "timestamp": "2026-01-01T00:00:00Z",
            "cpu_usage_percent": 1.0,
            "ram_usage_percent": 2.0,
            "disk_usage_percent": 3.0,
            "load_avg": {"1m": 0.1, "5m": 0.1, "15m": 0.1, "cores": 2},
            "uptime_seconds": 1234.5,
            "services": {"apache2": "active", "nginx": "active", "ssh": "active"},
            "tcp_ports": [],
            "network": "reachable",
            "http_apache_8080": 200,
            "http_nginx_80": 200,
        }
        with patch.dict(os.environ, {"HEALTH_LOCAL_MODE": "1"}, clear=True):
            with patch.object(local_health, "_random", return_value=fake_checks):
                with patch.object(sys, "argv", ["local_health.py", "server1"]):
                    with patch("builtins.print") as mock_print:
                        local_health.main()
        printed = "".join(args[0] for args, _ in mock_print.call_args_list)
        data = json.loads(printed)
        self.assertIn("overall", data)
        self.assertIn("hosts", data)
        self.assertEqual(data["hosts"][0]["host"], "server1")


class TestTelegramBot(unittest.TestCase):
    def test_help_command(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        self.assertIn("/health", telegram_bot.help_text())

    def test_status_command(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        fake_stdout = json.dumps({
            "overall": "HEALTHY",
            "hosts": [{
                "host": "server1",
                "timestamp": "2026-01-01T00:00:00Z",
                "overall": "HEALTHY",
                "warnings": [],
                "failed_checks": [],
                "checks": {
                    "host": "server1",
                    "cpu_usage_percent": 10.0,
                    "ram_usage_percent": 20.0,
                    "disk_usage_percent": 30.0,
                    "load_avg": {"1m": 0.1, "5m": 0.1, "15m": 0.1, "cores": 2},
                    "services": {"apache2": "active", "nginx": "active", "ssh": "active"},
                    "network": "reachable",
                    "http_apache_8080": 200,
                    "http_nginx_80": 200,
                },
            }],
        })

        class FakeCompleted:
            returncode = 0
            stdout = fake_stdout
            stderr = ""

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot.subprocess, "run", return_value=FakeCompleted()):
                with patch.object(telegram_bot, "send_message") as mock_send:
                    telegram_bot.handle_update({"message": {"chat": {"id": 1}, "text": "/status"}}, "dummy")
                    text = mock_send.call_args[0][1]
        self.assertIn("Triage Report", text)
        self.assertIn("HEALTHY", text)

    def test_unknown_command(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 1}, "text": "/unknown"}}, "dummy")
                text = mock_send.call_args[0][1]
        self.assertIn("Unknown command", text)

    def test_missing_token(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        with self.assertRaises(SystemExit):
            telegram_bot.main(["--mode", "cli", "--text", "/health"])

    def test_actions_list(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 1}, "text": "/actions"}}, "dummy")
                text = mock_send.call_args[0][1]
        self.assertIn("Approved actions", text)
        self.assertIn("restart_apache", text)

    def test_do_confirm_audit_flow(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 7}, "text": "/do restart_nginx server1"}}, "dummy")
                reply = mock_send.call_args[0][1]
        self.assertIn("restart_nginx", reply)
        self.assertIn("Confirm with /confirm restart_nginx server1", reply)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 7}, "text": "/confirm restart_nginx server1"}}, "dummy")
                reply = mock_send.call_args[0][1]
        self.assertIn("Executed", reply)
        self.assertIn("restart_nginx", reply)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 7}, "text": "/audit 5"}}, "dummy")
                reply = mock_send.call_args[0][1]
        self.assertIn("Action audit", reply)
        self.assertIn("restart_nginx", reply)

    def test_logs_export_retention(self):
        telegram_bot = _load_module("telegram_bot", "telegram_bot.py")
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 1}, "text": "/logs 5"}}, "dummy")
                text = mock_send.call_args[0][1]
        self.assertIn("Recent logs", text)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 1}, "text": "/export"}}, "dummy")
                text = mock_send.call_args[0][1]
        self.assertIn("Snapshot saved", text)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "dummy"}, clear=True):
            with patch.object(telegram_bot, "send_message") as mock_send:
                telegram_bot.handle_update({"message": {"chat": {"id": 1}, "text": "/retention"}}, "dummy")
                text = mock_send.call_args[0][1]
        self.assertIn("Retention cleanup complete", text)


class TestTriage(unittest.TestCase):
    def test_history_empty(self):
        triage = _load_module("triage", "triage.py")
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "index.json"
            with patch.object(triage, "REPORTS_INDEX", index_path):
                result = triage.history_tail(limit=5)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["entries"], [])

    def test_append_and_history(self):
        triage = _load_module("triage", "triage.py")
        payload = {
            "overall": "HEALTHY",
            "hosts": [
                {
                    "host": "server1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "overall": "HEALTHY",
                    "failed_checks": [],
                    "warnings": [],
                    "checks": {"host": "server1"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "index.json"
            with patch.object(triage, "REPORTS_INDEX", index_path):
                entry = triage.append_report(payload)
                self.assertEqual(entry["overall"], "HEALTHY")
                self.assertEqual(entry["server"], "server1")
                result = triage.history_tail(limit=5)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entries"][0]["overall"], "HEALTHY")


class TestActions(unittest.TestCase):
    def test_allowlist(self):
        actions = _load_module("actions", "actions.py")
        items = actions.list_actions()
        self.assertEqual([item["action"] for item in items], ["restart_apache", "restart_nginx", "clear_logs", "show_logs"])

    def test_do_confirm_audit(self):
        actions = _load_module("actions", "actions.py")
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "actions_index.json"
            with patch.object(actions, "ACTIONS_INDEX", index_path):
                requested = actions.request_action("1", "restart_apache", "server1")
                self.assertEqual(requested["status"], "pending_confirmation")
                confirmed = actions.confirm_action("1", "restart_apache", "server1")
                self.assertEqual(confirmed["status"], "executed")
                history = actions.action_history(limit=5)
        self.assertEqual(history["count"], 1)
        self.assertEqual(history["entries"][0]["action"], "restart_apache")

    def test_cancel(self):
        actions = _load_module("actions", "actions.py")
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "actions_index.json"
            with patch.object(actions, "ACTIONS_INDEX", index_path):
                actions.request_action("2", "show_logs", "server1")
                cancelled = actions.cancel_action("2", "show_logs", "server1")
        self.assertEqual(cancelled["status"], "cancelled")


class TestObservability(unittest.TestCase):
    def test_combined_logs_empty(self):
        observability = _load_module("observability", "observability.py")
        with tempfile.TemporaryDirectory() as tmp:
            health_path = Path(tmp) / "reports_index.json"
            actions_path = Path(tmp) / "actions_index.json"
            with patch.object(observability, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "ACTIONS_INDEX", actions_path):
                logs = observability.combined_logs(limit=5)
        self.assertEqual(logs, [])

    def test_export_snapshot(self):
        observability = _load_module("observability", "observability.py")
        with tempfile.TemporaryDirectory() as tmp:
            health_path = Path(tmp) / "reports_index.json"
            actions_path = Path(tmp) / "actions_index.json"
            with patch.object(observability, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "ACTIONS_INDEX", actions_path):
                snapshot = observability.export_snapshot()
        self.assertIn("timestamp", snapshot)
        self.assertIn("trends", snapshot)
        self.assertEqual(snapshot["trends"]["status"], "no_history")

    def test_retention(self):
        observability = _load_module("observability", "observability.py")
        entries = [
            {"timestamp": "2026-01-01T00:00:00Z", "overall": "HEALTHY"},
            {"timestamp": "2026-01-02T00:00:00Z", "overall": "WARNING"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            health_path = Path(tmp) / "reports_index.json"
            actions_path = Path(tmp) / "actions_index.json"
            health_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
            actions_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
            with patch.object(observability, "REPORTS_INDEX", health_path), \
                 patch.object(observability, "ACTIONS_INDEX", actions_path):
                result = observability.retention_cleanup(keep=1)
        self.assertEqual(result["health_pruned"], 1)
        self.assertEqual(result["actions_pruned"], 1)


if __name__ == "__main__":
    unittest.main()
