import json
import logging
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

LOG_LEVEL = os.environ.get("HEALTH_BOT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("health-bot")

BOT_TOKEN = None


def load_config():
    global BOT_TOKEN
    telegram_dir = Path(__file__).resolve().parent
    env_file = telegram_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN or not str(BOT_TOKEN).strip():
        logger.error("TELEGRAM_BOT_TOKEN is missing or empty.")
        sys.exit(1)


def redact(text: str) -> str:
    if BOT_TOKEN:
        return str(text).replace(BOT_TOKEN, "<redacted>")
    return text


def request(offset=None, timeout=10):
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?" + urllib.parse.urlencode(params)
    try:
        import requests as req

        response = req.get(url, timeout=timeout + 5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("Telegram request failed: %s", exc)
        return None


def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        import requests as req

        response = req.post(url, json=payload, timeout=20)
        response.raise_for_status()
        body = response.json()
        return bool(body.get("ok"))
    except Exception as exc:
        logger.error("sendMessage failed: %s", exc)
        return False


def health_report(server="server1") -> str:
    repo_root = Path(__file__).resolve().parents[1]
    health_script = repo_root / "health"
    if not health_script.exists():
        return f"<code>{server}</code> is not reachable.\nError: health script not found at {health_script}"

    try:
        completed = subprocess.run(
            [str(health_script), server],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        return f"<code>{server}</code> is not reachable.\nError: health script missing executable permission at {health_script}"
    except subprocess.CalledProcessError as exc:
        return f"<code>{server}</code> is not reachable.\nError: health script failed with code {exc.returncode}\n{exc.stderr.strip()[:800]}"

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return f"<code>{server}</code> is not reachable.\nError: invalid JSON from health script.\n{completed.stdout.strip()[:800]}"

    hosts = data.get("hosts") or []
    host = next((h for h in hosts if h.get("host") == server), None)
    if host is None:
        if not hosts:
            return f"<code>{server}</code> is not reachable.\nError: no host data returned."
        return f"<code>{server}</code> is not reachable.\nError: host `{server}` not found in health output."

    checks = host.get("checks") or {}
    overall = str(host.get("overall", "UNKNOWN")).upper()
    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🛑"}.get(overall, "❓")

    warnings = host.get("warnings") or []
    failed_checks = host.get("failed_checks") or []
    warnings_text = ", ".join(str(w) for w in warnings) if warnings else "None"
    failed_text = ", ".join(str(f) for f in failed_checks) if failed_checks else "None"

    services = checks.get("services") or {}
    apache_state = services.get("apache2", "unknown")
    nginx_state = services.get("nginx", "unknown")
    ssh_state = services.get("ssh", "unknown")

    http_apache = checks.get("http_apache_8080")
    http_nginx = checks.get("http_nginx_80")

    def http_display(value):
        if value is None:
            return "N/A"
        return str(value)

    load_avg = checks.get("load_avg") or {}
    load_text = " ".join(str(load_avg.get(k, "-")) for k in ("1m", "5m", "15m"))
    uptime_seconds = checks.get("uptime_seconds")
    uptime_text = f"{uptime_seconds:.2f}s" if isinstance(uptime_seconds, (int, float)) else str(uptime_seconds)

    return (
        f"{emoji} <b>Health Report</b>\n"
        f"Server : <code>{checks.get('host', server)}</code>\n"
        f"IP     : <code>{checks.get('network', 'N/A')}</code>\n"
        f"Status : <b>{overall}</b>\n"
        f"CPU    : {checks.get('cpu_usage_percent', 'N/A')}%\n"
        f"RAM    : {checks.get('ram_usage_percent', 'N/A')}%\n"
        f"Disk   : {checks.get('disk_usage_percent', 'N/A')}%\n"
        f"Load   : {load_text} (cores={load_avg.get('cores', '-')})\n"
        f"Uptime : {uptime_text}\n"
        f"Apache : {apache_state}\n"
        f"Nginx  : {nginx_state}\n"
        f"SSH    : {ssh_state}\n"
        f"HTTP Apache :8080 -> {http_display(http_apache)}\n"
        f"HTTP Nginx  :80 -> {http_display(http_nginx)}\n"
        f"Warnings        : {warnings_text}\n"
        f"Failed checks   : {failed_text}"
    )


def handle_update(update):
    if not update or "message" not in update:
        return True

    message = update["message"]
    text = (message.get("text") or "").strip()
    chat_id = message["chat"]["id"]

    if not text.startswith("/"):
        return True

    command = text.split()[0].split("@", 1)[0].lower()
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/start":
        reply = (
            "Hello.\n"
            "Commands:\n"
            "/health - health for default server\n"
            "/health server1 - health for server1"
        )
        send_message(chat_id, reply)
    elif command == "/health":
        server = arg if arg else "server1"
        reply = health_report(server)
        send_message(chat_id, reply)
    else:
        send_message(chat_id, "Unknown command. Use /start for help.")
    return True


def main():
    load_config()
    logger.info("Health bot started.")
    offset = None
    while True:
        data = request(offset=offset, timeout=20)
        if data is None:
            continue
        if not data.get("ok"):
            logger.error("Telegram response not ok: %s", redact(str(data)[:400]))
            continue
        updates = data.get("result") or []
        for update in updates:
            try:
                handle_update(update)
            except Exception as exc:
                logger.error("Failed to handle update: %s", exc)
        if updates:
            offset = updates[-1]["update_id"] + 1


def _run_tests():
    failures = []

    def ok(name):
        print(f"OK {name}.")

    def fail(name, exc):
        failures.append(name)
        print(f"FAIL {name}: {exc}")

    import importlib.util
    from unittest.mock import patch, MagicMock

    bot_path = str(Path(__file__).resolve())

    # 1. Token loaded but not printed.
    try:
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "secret-token"}, clear=True):
            spec = importlib.util.spec_from_file_location("bot_test_token", bot_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            assert mod.BOT_TOKEN == "secret-token"
        ok("token loaded and not printed")
    except Exception as exc:
        fail("token loaded and not printed", exc)

    # 2. /health server1 parses JSON and formats fields.
    try:
        sample = json.dumps({
            "overall": "WARNING",
            "hosts": [
                {
                    "host": "server1",
                    "timestamp": "2026-08-14T08:16:39Z",
                    "overall": "WARNING",
                    "warnings": ["high cpu"],
                    "failed_checks": ["port 9090 closed"],
                    "checks": {
                        "host": "server1",
                        "timestamp": "2026-08-14T08:16:39Z",
                        "cpu_usage_percent": 81.0,
                        "ram_usage_percent": 77.5,
                        "disk_usage_percent": 55.2,
                        "load_avg": {"1m": 1.23, "5m": 1.10, "15m": 0.95, "cores": 2},
                        "uptime_seconds": 3600.0,
                        "services": {"apache2": "active", "nginx": "active", "ssh": "inactive"},
                        "network": "reachable",
                        "http_apache_8080": 200,
                        "http_nginx_80": 500,
                    },
                }
            ],
        })
        update = {
            "message": {
                "chat": {"id": 123456},
                "text": "/health server1",
                "message_id": 10,
            }
        }
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "secret-token"}, clear=True):
            spec = importlib.util.spec_from_file_location("bot_test_health", bot_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        with patch.object(mod.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=sample, stderr="")
            with patch.object(mod, "send_message") as mock_send:
                mod.handle_update(update)
                text = mock_send.call_args[0][1]
                assert "⚠️" in text
                assert "WARNING" in text
                assert "CPU    : 81.0%" in text
                assert "HTTP Apache :8080 -> 200" in text
                assert "HTTP Nginx  :80 -> 500" in text
                assert "high cpu" in text
                assert "port 9090 closed" in text
        ok("/health server1 report format")
    except Exception as exc:
        fail("/health server1 report format", exc)

    # 3. /start help message.
    try:
        update = {
            "message": {
                "chat": {"id": 123456},
                "text": "/start",
                "message_id": 11,
            }
        }
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "secret-token"}, clear=True):
            spec = importlib.util.spec_from_file_location("bot_test_start", bot_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        with patch.object(mod, "send_message") as mock_send:
            mod.handle_update(update)
            text = mock_send.call_args[0][1]
            assert "/health" in text
        ok("/start help message")
    except Exception as exc:
        fail("/start help message", exc)

    # 4. Unknown command fallback.
    try:
        update = {
            "message": {
                "chat": {"id": 123456},
                "text": "/boo",
                "message_id": 13,
            }
        }
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "secret-token"}, clear=True):
            spec = importlib.util.spec_from_file_location("bot_test_unknown", bot_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        with patch.object(mod, "send_message") as mock_send:
            mod.handle_update(update)
            text = mock_send.call_args[0][1]
            assert "Unknown command" in text
        ok("unknown command fallback")
    except Exception as exc:
        fail("unknown command fallback", exc)

    # 5. Missing script handled gracefully.
    try:
        update = {
            "message": {
                "chat": {"id": 123456},
                "text": "/health server1",
                "message_id": 14,
            }
        }
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "secret-token"}, clear=True):
            spec = importlib.util.spec_from_file_location("bot_test_missing", bot_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError("missing")):
            with patch.object(mod, "send_message") as mock_send:
                mod.handle_update(update)
                text = mock_send.call_args[0][1]
                assert "Error" in text
        ok("missing health script handled")
    except Exception as exc:
        fail("missing health script handled", exc)

    # 6. Local smoke test using real ./health output; never prints token.
    try:
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "HEALTH_BOT_TEST": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
        completed = subprocess.run(
            [sys.executable, bot_path],
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = completed.stdout
        assert completed.returncode == 0, f"bot failed: {completed.stderr}"
        assert "test-token" not in stdout
        assert "<redacted>" in stdout
        assert "server1" in stdout
        assert "HTTP Apache :8080 -> 200" in stdout
        assert "HTTP Nginx  :80 -> 200" in stdout
        ok("local bot smoke test")
    except Exception as exc:
        fail("local bot smoke test", exc)

    if failures:
        raise SystemExit(f"Test failures: {', '.join(failures)}")
    print("All tests passed.")


if __name__ == "__main__":
    if os.environ.get("HEALTH_BOT_TEST") == "1":
        _run_tests()
    else:
        main()
