#!/usr/bin/env python3
"""Phase 3 safe action gateway: allowlisted actions with confirmation and audit logging."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIONS_DIR = PROJECT_ROOT / "monitoring" / "reports"
ACTIONS_INDEX = ACTIONS_DIR / "actions_index.json"

ACTION_ALLOWLIST = {
    "restart_apache": {
        "name": "Restart Apache",
        "description": "Restart Apache service on the target host.",
        "risk": "medium",
    },
    "restart_nginx": {
        "name": "Restart Nginx",
        "description": "Restart Nginx service on the target host.",
        "risk": "medium",
    },
    "clear_logs": {
        "name": "Clear rotated logs",
        "description": "Clear safe rotated log files.",
        "risk": "low",
    },
    "show_logs": {
        "name": "Show recent logs",
        "description": "Show recent service log entries.",
        "risk": "low",
    },
}

_pending: Dict[str, Dict[str, Any]] = {}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs():
    ACTIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_index() -> List[Dict[str, Any]]:
    if not ACTIONS_INDEX.exists():
        return []
    try:
        text = ACTIONS_INDEX.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return json.loads(text)
    except Exception:
        return []


def save_index(index: List[Dict[str, Any]]) -> None:
    _ensure_dirs()
    ACTIONS_INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def log_action(entry: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_dirs()
    index = load_index()
    index.append(entry)
    save_index(index)
    return entry


def list_actions() -> List[Dict[str, Any]]:
    return [
        {"action": key, **value}
        for key, value in ACTION_ALLOWLIST.items()
    ]


def request_action(chat_id: str, action: str, server: str) -> Dict[str, Any]:
    if action not in ACTION_ALLOWLIST:
        raise ValueError(f"Action '{action}' is not approved.")
    key = f"{chat_id}:{action}:{server}"
    _pending[key] = {
        "chat_id": chat_id,
        "action": action,
        "server": server,
        "status": "pending",
        "requested_at": _now(),
    }
    return {
        "status": "pending_confirmation",
        "key": key,
        "action": action,
        "server": server,
        "risk": ACTION_ALLOWLIST[action]["risk"],
        "description": ACTION_ALLOWLIST[action]["description"],
    }


def confirm_action(chat_id: str, action: str, server: str) -> Dict[str, Any]:
    key = f"{chat_id}:{action}:{server}"
    pending = _pending.get(key)
    if not pending:
        return {"status": "not_found", "action": action, "server": server}
    result = execute_mock_action(action, server)
    entry = {
        "timestamp": _now(),
        "chat_id": chat_id,
        "action": action,
        "server": server,
        "status": "executed",
        "result": result,
        "source": "mock",
    }
    log_action(entry)
    _pending.pop(key, None)
    return {"status": "executed", "action": action, "server": server, "result": result}


def cancel_action(chat_id: str, action: str, server: str) -> Dict[str, Any]:
    key = f"{chat_id}:{action}:{server}"
    pending = _pending.pop(key, None)
    if not pending:
        return {"status": "not_found", "action": action, "server": server}
    return {"status": "cancelled", "action": action, "server": server}


def execute_mock_action(action: str, server: str) -> Dict[str, Any]:
    if action == "restart_apache":
        return {
            "ok": True,
            "changed": True,
            "stdout": f"mock: apache2 restarted on {server}",
            "stderr": "",
        }
    if action == "restart_nginx":
        return {
            "ok": True,
            "changed": True,
            "stdout": f"mock: nginx restarted on {server}",
            "stderr": "",
        }
    if action == "clear_logs":
        return {
            "ok": True,
            "changed": True,
            "stdout": f"mock: cleared safe log files on {server}",
            "stderr": "",
        }
    if action == "show_logs":
        return {
            "ok": True,
            "changed": False,
            "stdout": f"[{server}] mock log line 1\n[{server}] mock log line 2",
            "stderr": "",
        }
    raise ValueError(f"Unsupported action: {action}")


def action_history(limit: int = 10) -> Dict[str, Any]:
    index = load_index()
    recent = index[-limit:] if index else []
    return {"count": len(recent), "entries": recent}
