#!/usr/bin/env python3
"""Phase 4 observability: unified logs, export, retention."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "monitoring" / "reports"
REPORTS_INDEX = REPORTS_DIR / "reports_index.json"
ACTIONS_INDEX = REPORTS_DIR / "actions_index.json"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path):
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return json.loads(text)
    except Exception:
        return []


def combined_logs(limit: int = 20) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for path in (REPORTS_INDEX, ACTIONS_INDEX):
        for entry in _read_json(path):
            event = dict(entry)
            event["source"] = path.name
            events.append(event)
    events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return events[: max(1, limit)]


def export_snapshot() -> Dict[str, Any]:
    health = _read_json(REPORTS_INDEX)
    actions = _read_json(ACTIONS_INDEX)
    return {
        "timestamp": _now(),
        "health_events": health[-20:],
        "action_events": actions[-20:],
        "trends": _trends(health),
        "action_summary": _action_summary(actions),
    }


def _trends(health_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not health_events:
        return {"status": "no_history"}
    by_status: Dict[str, int] = {}
    for entry in health_events:
        status = entry.get("overall", "UNKNOWN")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "samples": len(health_events),
        "oldest": health_events[0].get("timestamp"),
        "latest": health_events[-1].get("timestamp"),
        "by_status": by_status,
    }


def _action_summary(action_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not action_events:
        return {"status": "no_history"}
    by_action: Dict[str, int] = {}
    for entry in action_events:
        action = entry.get("action", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
    return {
        "samples": len(action_events),
        "by_action": by_action,
        "latest": action_events[-1].get("timestamp"),
    }


def prune(path: Path, keep: int = 100) -> int:
    events = _read_json(path)
    if len(events) <= keep:
        return 0
    trimmed = events[-keep:]
    try:
        path.write_text(json.dumps(trimmed, indent=2) + "\n", encoding="utf-8")
        return len(events) - len(trimmed)
    except Exception:
        return -1


def retention_cleanup(keep: int = 100) -> Dict[str, int]:
    return {
        "health_pruned": prune(REPORTS_INDEX, keep=keep),
        "actions_pruned": prune(ACTIONS_INDEX, keep=keep),
    }
