#!/usr/bin/env python3
"""Telegram bot skeleton for AI DevOps Command Center Phase 2."""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
LOCAL_HEALTH_PY = PROJECT_ROOT / "monitoring" / "local_health.py"
REPORTS_DIR = PROJECT_ROOT / "monitoring" / "reports"
DEFAULT_MESSAGE = (
    "Hello.\n"
    "Commands:\n"
    "/health - health for default server\n"
    "/health server1 - health for server1\n"
    "/status [server] - triage summary\n"
    "/history [n] - recent health history\n"
    "/logs [n] - recent combined logs\n"
    "/actions - list approved actions\n"
    "/do <action> [server] - request an action\n"
    "/confirm <action> [server] - confirm pending action\n"
    "/cancel <action> [server] - cancel pending action\n"
    "/audit [n] - recent action history\n"
    "/export - JSON snapshot\n"
    "/retention - prune old logs\n"
    "/help - command reference"
)

LOG_LEVEL = os.environ.get("HEALTH_BOT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("health-bot")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Telegram health bot")
    parser.add_argument("--mode", choices=["interactive", "cli"], default="interactive")
    parser.add_argument("--text", default="")
    parser.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    return parser.parse_args(argv)


def send_message(chat_id: int, text: str, token: str) -> bool:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        import requests as req

        response = req.post(url, json=payload, timeout=20)
        response.raise_for_status()
        body = response.json()
        return bool(body.get("ok"))
    except Exception as exc:
        logger.error("sendMessage failed: %s", exc)
        return False


def request_telegram(token: str, offset=None, timeout=10):
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{token}/getUpdates?" + __import__("urllib.parse", fromlist=["urlencode"]).parse.urlencode(params)
    try:
        import requests as req

        response = req.get(url, timeout=timeout + 5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("Telegram request failed: %s", exc)
        return None


def _run_local_health(server: str = "server1") -> dict:
    if not LOCAL_HEALTH_PY.exists():
        raise FileNotFoundError(f"missing {LOCAL_HEALTH_PY}")
    completed = subprocess.run(
        [sys.executable, str(LOCAL_HEALTH_PY), server],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(completed.stdout)
    hosts = data.get("hosts") or []
    host = next((h for h in hosts if h.get("host") == server), hosts[0] if hosts else {})
    return host


def health_report(server: str = "server1") -> str:
    try:
        host = _run_local_health(server)
    except FileNotFoundError as exc:
        return f"<code>{server}</code>\nError: {exc}"
    except subprocess.CalledProcessError as exc:
        return f"<code>{server}</code>\nError: health failed with code {exc.returncode}\n{exc.stderr.strip()[:800]}"
    except json.JSONDecodeError:
        return f"<code>{server}</code>\nError: invalid health JSON."

    checks = host.get("checks") or {}
    overall = str(host.get("overall", "UNKNOWN")).upper()
    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🛑"}.get(overall, "❓")
    warnings = host.get("warnings") or []
    failed_checks = host.get("failed_checks") or []
    warnings_text = ", ".join(str(w) for w in warnings) if warnings else "None"
    failed_text = ", ".join(str(f) for f in failed_checks) if failed_checks else "None"
    services = checks.get("services") or {}
    load_avg = checks.get("load_avg") or {}

    return (
        f"{emoji} <b>Health Report</b>\n"
        f"Server : <code>{checks.get('host', server)}</code>\n"
        f"Status : <b>{overall}</b>\n"
        f"CPU    : {checks.get('cpu_usage_percent', 'N/A')}%\n"
        f"RAM    : {checks.get('ram_usage_percent', 'N/A')}%\n"
        f"Disk   : {checks.get('disk_usage_percent', 'N/A')}%\n"
        f"Load   : {load_avg.get('1m', '-')} {load_avg.get('5m', '-')} {load_avg.get('15m', '-')} (cores={load_avg.get('cores', '-')})\n"
        f"Apache : {services.get('apache2', 'unknown')}\n"
        f"Nginx  : {services.get('nginx', 'unknown')}\n"
        f"SSH    : {services.get('ssh', 'unknown')}\n"
        f"Warnings      : {warnings_text}\n"
        f"Failed checks : {failed_text}"
    )


def status_report(server: str = "server1") -> str:
    try:
        from monitoring.triage import triage

        host = _run_local_health(server)
        summary = triage({"hosts": [host]})
    except Exception as exc:
        logger.error("triage failed: %s", exc)
        return f"<code>{server}</code> status unavailable: {exc}"

    overall = str(summary.get("overall", host.get("overall", "UNKNOWN"))).upper()
    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🛑"}.get(overall, "❓")
    risk = str(summary.get("risk_level", "unknown")).lower()
    risks = summary.get("top_risks") or ["No immediate risks detected"]
    actions = summary.get("primary_actions") or ["Continue monitoring"]
    rationale = summary.get("rationale") or []
    lines = [
        f"{emoji} <b>Triage Report</b>",
        f"Server : <code>{summary.get('server', server)}</code>",
        f"Status : <b>{overall}</b>",
        f"Risk   : {risk}",
        "",
        "<b>Top risks</b>",
    ]
    lines.extend([f"- {item}" for item in risks[:5]])
    lines.append("")
    lines.append("<b>Rationale</b>")
    lines.extend([f"- {item}" for item in rationale[:3]] if rationale else ["- None"])
    lines.append("")
    lines.append("<b>Suggested next checks</b>")
    lines.extend([f"- {item}" for item in actions[:5]])
    return "\n".join(lines)


def history_report(limit: int = 10) -> str:
    try:
        from monitoring.triage import history_tail

        data = history_tail(limit=limit)
    except Exception as exc:
        return f"History unavailable: {exc}"

    entries = data.get("entries") or []
    if not entries:
        return "No history yet. Run /health or /status first."
    lines = [f"<b>Recent history</b> ({data.get('count')}/{limit})", ""]
    for entry in entries[-limit:]:
        timestamp = entry.get("timestamp", "-")
        overall = str(entry.get("overall", "UNKNOWN")).upper()
        server = entry.get("server", "server1")
        emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🛑"}.get(overall, "❓")
        failed = entry.get("failed_checks") or []
        warnings = entry.get("warnings") or []
        lines.append(f"{emoji} <code>{server}</code> {timestamp} {overall}")
        if failed:
            lines.append(f"  failed: {', '.join(str(x) for x in failed[:3])}")
        if warnings:
            lines.append(f"  warnings: {', '.join(str(x) for x in warnings[:3])}")
    return "\n".join(lines)


def actions_report() -> str:
    try:
        from monitoring.actions import list_actions

        items = list_actions()
    except Exception as exc:
        return f"Actions unavailable: {exc}"
    if not items:
        return "No approved actions."
    lines = ["<b>Approved actions</b>", ""]
    for item in items:
        lines.append(f"- {item['action']}: {item['name']} ({item['risk']})")
        lines.append(f"  {item['description']}")
    return "\n".join(lines)


def _parse_action_arg(arg: str):
    parts = arg.split(maxsplit=1)
    action = parts[0] if parts else ""
    server = parts[1].strip() if len(parts) > 1 else "server1"
    return action, server


def do_action(chat_id, action: str, server: str) -> str:
    try:
        from monitoring.actions import request_action

        result = request_action(str(chat_id), action, server)
    except Exception as exc:
        return f"Action request failed: {exc}"
    if result.get("status") != "pending_confirmation":
        return f"Action '{action}' is not approved."
    return (
        f"Action: <b>{action}</b>\n"
        f"Server: <code>{server}</code>\n"
        f"Risk  : {result.get('risk')}\n"
        f"Description: {result.get('description')}\n"
        f"Confirm with /confirm {action} {server}\n"
        f"Cancel with /cancel {action} {server}"
    )


def confirm_action(chat_id, action: str, server: str) -> str:
    try:
        from monitoring.actions import confirm_action as _confirm

        result = _confirm(str(chat_id), action, server)
    except Exception as exc:
        return f"Action confirmation failed: {exc}"
    status = result.get("status")
    if status == "not_found":
        return f"No pending action for {action} on {server}. Request it with /do {action} {server}."
    executed = result.get("result") or {}
    changed = executed.get("changed", False)
    return (
        f"Executed: <b>{action}</b> on <code>{server}</code>\n"
        f"Changed : {changed}\n"
        f"Output  : {executed.get('stdout', '').strip()[:300]}"
    )


def cancel_action(chat_id, action: str, server: str) -> str:
    try:
        from monitoring.actions import cancel_action as _cancel

        result = _cancel(str(chat_id), action, server)
    except Exception as exc:
        return f"Action cancellation failed: {exc}"
    status = result.get("status")
    if status == "not_found":
        return f"No pending action for {action} on {server}."
    return f"Cancelled: {action} on {server}."


def confirm_action_reply(chat_id, action: str, server: str) -> str:
    return confirm_action(chat_id, action, server)


def cancel_action_reply(chat_id, action: str, server: str) -> str:
    return cancel_action(chat_id, action, server)


def audit_report(limit: int = 10) -> str:
    try:
        from monitoring.actions import action_history

        data = action_history(limit=limit)
    except Exception as exc:
        return f"Audit unavailable: {exc}"
    entries = data.get("entries") or []
    if not entries:
        return "No action history yet."
    lines = [f"<b>Action audit</b> ({data.get('count')}/{limit})", ""]
    for entry in entries[-limit:]:
        lines.append(
            f"{entry.get('timestamp')} | {entry.get('action')} | {entry.get('server')} | {entry.get('status')}"
        )
    return "\n".join(lines)


def logs_report(limit: int = 20) -> str:
    try:
        from monitoring.observability import combined_logs

        entries = combined_logs(limit=limit)
    except Exception as exc:
        return f"Logs unavailable: {exc}"
    if not entries:
        return "No logs yet."
    lines = [f"<b>Recent logs</b> ({len(entries)}/{limit})", ""]
    for entry in entries[:limit]:
        source = entry.get("source", "-")
        timestamp = entry.get("timestamp", "-")
        overall = str(entry.get("overall", entry.get("status", "-"))).upper()
        server = entry.get("server", "-")
        lines.append(f"{timestamp} | {source} | <code>{server}</code> | {overall}")
    return "\n".join(lines)


def export_report() -> str:
    try:
        from monitoring.observability import export_snapshot

        snapshot = export_snapshot()
    except Exception as exc:
        return f"Export unavailable: {exc}"
    path = REPORTS_DIR / "snapshot.json"
    try:
        path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        return f"Export failed: {exc}"
    return f"Snapshot saved to {path}"


def retention_report() -> str:
    try:
        from monitoring.observability import retention_cleanup

        result = retention_cleanup(keep=100)
    except Exception as exc:
        return f"Retention unavailable: {exc}"
    return (
        "Retention cleanup complete.\n"
        f"Health pruned : {result.get('health_pruned', 0)}\n"
        f"Actions pruned: {result.get('actions_pruned', 0)}"
    )


def help_text() -> str:
    return (
        "<b>AI DevOps Command Center</b>\n"
        "/health [server] - full health report\n"
        "/status [server] - triage summary\n"
        "/history [n] - recent health history\n"
        "/logs [n] - recent combined logs\n"
        "/actions - list approved actions\n"
        "/do <action> [server] - request an action\n"
        "/confirm <action> [server] - confirm pending action\n"
        "/cancel <action> [server] - cancel pending action\n"
        "/audit [n] - recent action history\n"
        "/export - JSON snapshot\n"
        "/retention - prune old logs\n"
        "/help - this message"
    )


def handle_update(update, token: str):
    if not update or "message" not in update:
        return

    message = update["message"]
    text = (message.get("text") or "").strip()
    chat_id = message["chat"]["id"]

    if not text.startswith("/"):
        return

    command = text.split()[0].split("@", 1)[0].lower()
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/start":
        send_message(chat_id, DEFAULT_MESSAGE, token)
    elif command == "/help":
        send_message(chat_id, help_text(), token)
    elif command == "/health":
        server = arg if arg else "server1"
        send_message(chat_id, health_report(server), token)
    elif command == "/status":
        server = arg if arg else "server1"
        send_message(chat_id, status_report(server), token)
    elif command == "/history":
        limit = 10
        if arg:
            try:
                limit = max(1, min(50, int(arg)))
            except ValueError:
                limit = 10
        send_message(chat_id, history_report(limit), token)
    elif command == "/actions":
        send_message(chat_id, actions_report(), token)
    elif command == "/do":
        server = arg.split()[1] if " " in arg else "server1"
        action = arg.split()[0] if arg else ""
        send_message(chat_id, do_action(chat_id, action, server), token)
    elif command == "/confirm":
        server = arg.split()[1] if " " in arg else "server1"
        action = arg.split()[0] if arg else ""
        send_message(chat_id, confirm_action_reply(chat_id, action, server), token)
    elif command == "/cancel":
        server = arg.split()[1] if " " in arg else "server1"
        action = arg.split()[0] if arg else ""
        send_message(chat_id, cancel_action_reply(chat_id, action, server), token)
    elif command == "/audit":
        limit = 10
        if arg:
            try:
                limit = max(1, min(50, int(arg)))
            except ValueError:
                limit = 10
        send_message(chat_id, audit_report(limit), token)
    elif command == "/logs":
        limit = 20
        if arg:
            try:
                limit = max(1, min(50, int(arg)))
            except ValueError:
                limit = 20
        send_message(chat_id, logs_report(limit), token)
    elif command == "/export":
        send_message(chat_id, export_report(), token)
    elif command == "/retention":
        send_message(chat_id, retention_report(), token)
    else:
        send_message(chat_id, "Unknown command. Use /help for commands.", token)


def interactive(token: str):
    logger.info("Health bot started.")
    offset = None
    while True:
        data = request_telegram(token, offset=offset, timeout=20)
        if data is None:
            continue
        if not data.get("ok"):
            logger.error("Telegram response not ok: %s", str(data)[:400])
            continue
        updates = data.get("result") or []
        for update in updates:
            try:
                handle_update(update, token)
            except Exception as exc:
                logger.error("Failed to handle update: %s", exc)
        if updates:
            offset = updates[-1]["update_id"] + 1


def cli_mode(token: str, text: str):
    command = text.strip().lower()
    if command in {"/health", "/status"} or command.startswith("/health ") or command.startswith("/status "):
        server = text.split(maxsplit=1)[1].strip() if " " in text else "server1"
        if command.startswith("/health"):
            print(health_report(server))
        else:
            print(status_report(server))
    elif command == "/help":
        print(help_text())
    elif command == "/start":
        print(DEFAULT_MESSAGE)
    elif command == "/history":
        limit = 10
        rest = text.split(maxsplit=1)[1].strip() if " " in text else ""
        if rest:
            try:
                limit = max(1, min(50, int(rest)))
            except ValueError:
                limit = 10
        print(history_report(limit))
    elif command == "/logs":
        limit = 20
        rest = text.split(maxsplit=1)[1].strip() if " " in text else ""
        if rest:
            try:
                limit = max(1, min(50, int(rest)))
            except ValueError:
                limit = 20
        print(logs_report(limit))
    elif command == "/export":
        print(export_report())
    elif command == "/retention":
        print(retention_report())
    else:
        print("Unknown command. Use /help for commands.")


def main(argv=None):
    args = parse_args(argv)
    if not args.token:
        print("TELEGRAM_BOT_TOKEN is missing. Use --token or set TELEGRAM_BOT_TOKEN.", file=sys.stderr)
        raise SystemExit(2)
    if args.mode == "cli":
        cli_mode(args.token, args.text or "/health")
    else:
        interactive(args.token)


if __name__ == "__main__":
    main()
