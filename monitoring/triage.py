#!/usr/bin/env python3
"""Phase 2 triage brain: summarize health state, maintain report history, and suggest next checks."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "monitoring" / "reports"
REPORTS_INDEX = REPORTS_DIR / "reports_index.json"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_index() -> List[Dict]:
    if not REPORTS_INDEX.exists():
        return []
    try:
        text = REPORTS_INDEX.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return json.loads(text)
    except Exception:
        return []


def save_index(index: List[Dict]) -> None:
    _ensure_dirs()
    REPORTS_INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def append_report(payload: Dict) -> Dict:
    _ensure_dirs()
    index = load_index()
    host = (((payload.get("hosts") or [{}])[0]))
    entry = {
        "timestamp": payload.get("timestamp") or host.get("timestamp") or _now(),
        "overall": payload.get("overall") or host.get("overall") or "UNKNOWN",
        "server": payload.get("host") or payload.get("server") or host.get("host") or "server1",
        "failed_checks": payload.get("failed_checks") or host.get("failed_checks") or [],
        "warnings": payload.get("warnings") or host.get("warnings") or [],
        "source": payload.get("source", "local"),
    }
    index.append(entry)
    save_index(index)
    return entry


def summarize_host(host: Dict) -> Dict:
    checks = host.get("checks") or {}
    overall = str(host.get("overall", "UNKNOWN")).upper()
    warnings = host.get("warnings") or []
    failed = host.get("failed_checks") or []
    services = checks.get("services") or {}

    summary = {
        "server": checks.get("host") or host.get("host") or "server1",
        "timestamp": checks.get("timestamp") or host.get("timestamp") or _now(),
        "overall": overall,
        "risk_level": "low",
        "top_risks": [],
        "service_status": services,
        "primary_actions": [],
        "rationale": [],
    }

    risks = []
    if failed:
        summary["risk_level"] = "critical"
        risks.extend([f"CRITICAL: {item}" for item in failed])
    elif warnings:
        summary["risk_level"] = "elevated"
        risks.extend([f"WARNING: {item}" for item in warnings])

    cpu = float(checks.get("cpu_usage_percent", 0))
    ram = float(checks.get("ram_usage_percent", 0))
    disk = float(checks.get("disk_usage_percent", 0))
    load_1m = float((checks.get("load_avg") or {}).get("1m", 0))
    cores = int((checks.get("load_avg") or {}).get("cores", 1))
    apache_http = int(checks.get("http_apache_8080", 0))
    nginx_http = int(checks.get("http_nginx_80", 0))
    network = str(checks.get("network", "unknown"))

    if cpu >= 95 or ram >= 95 or disk >= 95:
        risks.append("Resource saturation detected")
    if network != "reachable":
        risks.append("Host network connectivity is degraded")
    if apache_http != 200 or nginx_http != 200:
        risks.append("Web path has HTTP errors")
    if services.get("apache2") != "active" or services.get("nginx") != "active":
        risks.append("Frontend path has inactive services")

    if cpu >= 80 or ram >= 80 or disk >= 80:
        summary["rationale"].append("Resource usage is elevated")
    if load_1m > cores * 2:
        summary["rationale"].append("Load is above 2x core warning threshold")
    if services.get("apache2") != "active":
        summary["primary_actions"].append("Check Apache unit logs: journalctl -u apache2")
    if services.get("nginx") != "active":
        summary["primary_actions"].append("Check Nginx unit logs: journalctl -u nginx")
    if services.get("ssh") != "active":
        summary["primary_actions"].append("SSH is inactive; verify sshd and access policy")
    if apache_http != 200:
        summary["primary_actions"].append("Apache on 8080 is not healthy; check app/backend and proxy config")
    if nginx_http != 200:
        summary["primary_actions"].append("Nginx on 80 is not healthy; check proxy_pass and upstream state")
    if network != "reachable":
        summary["primary_actions"].append("Verify host routing, firewall rules, and gateway reachability")

    summary["top_risks"] = risks[:5] if risks else ["No immediate risks detected"]
    if not summary["primary_actions"]:
        summary["primary_actions"] = ["Continue monitoring; no immediate action required"]

    return summary


def triage(payload: Dict, persist: bool = True) -> Dict:
    hosts = payload.get("hosts") or []
    host = next((h for h in hosts if h.get("host")), hosts[0] if hosts else {})
    summary = summarize_host(host)

    if persist:
        try:
            append_report(payload)
        except Exception as exc:
            summary["rationale"].append(f"History persistence failed: {exc}")

    return summary


def history_tail(limit: int = 10) -> Dict:
    index = load_index()
    recent = index[-limit:] if index else []
    return {
        "count": len(recent),
        "entries": recent,
    }


def trends() -> Dict:
    index = load_index()
    if not index:
        return {"status": "no_history"}
    by_status = {}
    for entry in index:
        by_status[entry.get("overall", "UNKNOWN")] = by_status.get(entry.get("overall", "UNKNOWN"), 0) + 1
    return {
        "samples": len(index),
        "oldest": index[0].get("timestamp"),
        "latest": index[-1].get("timestamp"),
        "by_status": by_status,
        "latest_entry": index[-1],
    }
