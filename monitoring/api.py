#!/usr/bin/env python3
"""Phase 5 structured JSON API wrapper for offline/automation consumers."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _read_json(path: Path):
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        return json.loads(text)
    except Exception:
        return {}


def _health_snapshot(server: str = "server1") -> Dict[str, Any]:
    try:
        from monitoring.triage import triage, append_report
    except Exception as exc:
        return {"ok": False, "error": f"import_failed: {exc}"}

    host = {}
    try:
        import subprocess

        completed = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "monitoring" / "local_health.py"), server],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(completed.stdout)
        hosts = payload.get("hosts") or []
        host = next((h for h in hosts if h.get("host") == server), hosts[0] if hosts else {})
        summary = triage({"hosts": [host]})
        report = append_report(payload)
    except Exception as exc:
        return {"ok": False, "error": f"health_failed: {exc}"}

    return {
        "ok": True,
        "server": server,
        "overall": host.get("overall", summary.get("overall", "UNKNOWN")).upper(),
        "report": report,
        "triage": summary,
        "host": host,
    }


def _action_allowlist() -> Dict[str, Any]:
    try:
        from monitoring.actions import list_actions

        items = list_actions()
    except Exception as exc:
        return {"ok": False, "error": f"actions_unavailable: {exc}"}
    return {"ok": True, "actions": items}


def _action_request(chat_id: str, action: str, server: str) -> Dict[str, Any]:
    try:
        from monitoring.actions import request_action

        result = request_action(chat_id, action, server)
    except Exception as exc:
        return {"ok": False, "error": f"request_failed: {exc}"}
    return {"ok": result.get("status") == "pending_confirmation", "request": result}


def _action_confirm(chat_id: str, action: str, server: str) -> Dict[str, Any]:
    try:
        from monitoring.actions import confirm_action as _confirm

        result = _confirm(chat_id, action, server)
    except Exception as exc:
        return {"ok": False, "error": f"confirm_failed: {exc}"}
    return {"ok": True, "result": result}


def _action_cancel(chat_id: str, action: str, server: str) -> Dict[str, Any]:
    try:
        from monitoring.actions import cancel_action as _cancel

        result = _cancel(chat_id, action, server)
    except Exception as exc:
        return {"ok": False, "error": f"cancel_failed: {exc}"}
    return {"ok": result.get("status") == "cancelled", "result": result}


def _action_history(limit: int = 10) -> Dict[str, Any]:
    try:
        from monitoring.actions import action_history

        data = action_history(limit=limit)
    except Exception as exc:
        return {"ok": False, "error": f"history_failed: {exc}"}
    return {"ok": True, "audit": data}


def _export_snapshot() -> Dict[str, Any]:
    try:
        from monitoring.observability import export_snapshot

        snapshot = export_snapshot()
    except Exception as exc:
        return {"ok": False, "error": f"export_failed: {exc}"}
    return {"ok": True, "snapshot": snapshot}


def _retention(keep: int = 100) -> Dict[str, Any]:
    try:
        from monitoring.observability import retention_cleanup

        result = retention_cleanup(keep=keep)
    except Exception as exc:
        return {"ok": False, "error": f"retention_failed: {exc}"}
    return {"ok": True, "retention": result}


def _dispatch(command: str, args: Dict[str, str]):
    command = (command or "").lower()
    if command == "health":
        return _health_snapshot(args.get("server", "server1"))
    if command == "allowlist":
        return _action_allowlist()
    if command == "do":
        return _action_request(str(args.get("chat_id", "")), str(args.get("action", "")), str(args.get("server", "server1")))
    if command == "confirm":
        return _action_confirm(str(args.get("chat_id", "")), str(args.get("action", "")), str(args.get("server", "server1")))
    if command == "cancel":
        return _action_cancel(str(args.get("chat_id", "")), str(args.get("action", "")), str(args.get("server", "server1")))
    if command == "audit":
        limit = 10
        raw = args.get("limit")
        if raw is not None:
            try:
                limit = max(1, min(50, int(raw)))
            except ValueError:
                limit = 10
        return _action_history(limit=limit)
    if command == "export":
        return _export_snapshot()
    if command == "retention":
        raw = args.get("keep")
        keep = 100
        if raw is not None:
            try:
                keep = max(1, int(raw))
            except ValueError:
                keep = 100
        return _retention(keep=keep)
    return {"ok": False, "error": f"unknown_command: {command}"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI DevOps Command Center JSON API")
    parser.add_argument("command", help="health|allowlist|do|confirm|cancel|audit|export|retention")
    parser.add_argument("--server", default="server1")
    parser.add_argument("--action", default="")
    parser.add_argument("--chat-id", default="cli")
    parser.add_argument("--limit", default="10")
    parser.add_argument("--keep", default="100")
    args = parser.parse_args(argv)
    payload = _dispatch(args.command, {
        "server": args.server,
        "action": args.action,
        "chat_id": args.chat_id,
        "limit": args.limit,
        "keep": args.keep,
    })
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
