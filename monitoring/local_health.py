#!/usr/bin/env python3
"""Local health fallback for Phase 1 offline verification."""

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "monitoring" / "config.yaml"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _random(server):
    return {
        "host": server,
        "timestamp": _now(),
        "cpu_usage_percent": round(random.uniform(2.0, 12.0), 1),
        "ram_usage_percent": round(random.uniform(30.0, 55.0), 1),
        "disk_usage_percent": round(random.uniform(20.0, 40.0), 1),
        "load_avg": {
            "1m": round(random.uniform(0.05, 0.25), 2),
            "5m": round(random.uniform(0.05, 0.2), 2),
            "15m": round(random.uniform(0.02, 0.15), 2),
            "cores": 2,
        },
        "uptime_seconds": round(random.uniform(1000, 50000), 2),
        "services": {
            "apache2": "active",
            "nginx": "active",
            "ssh": "active",
        },
        "tcp_ports": [
            "LISTEN 0 4096 0.0.0.0:80 0.0.0.0:* users:((\"nginx\",pid=1,fd=1))",
            "LISTEN 0 4096 127.0.0.1:8080 0.0.0.0:* users:((\"apache2\",pid=2,fd=1))",
        ],
        "network": "reachable",
        "http_apache_8080": 200,
        "http_nginx_80": 200,
    }


def evaluate(checks):
    cpu = float(checks.get("cpu_usage_percent", 0))
    ram = float(checks.get("ram_usage_percent", 0))
    disk = float(checks.get("disk_usage_percent", 0))
    load_1m = float((checks.get("load_avg") or {}).get("1m", 0))
    cores = int((checks.get("load_avg") or {}).get("cores", 1))
    services = checks.get("services") or {}
    network = str(checks.get("network", "unknown"))
    apache_http = int(checks.get("http_apache_8080", 0))
    nginx_http = int(checks.get("http_nginx_80", 0))

    warnings = []
    failed = []

    if cpu >= 95:
        failed.append(f"CPU usage {cpu:.1f}% >= 95%")
    elif cpu >= 80:
        warnings.append(f"CPU usage {cpu:.1f}% >= 80%")

    if ram >= 95:
        failed.append(f"RAM usage {ram:.1f}% >= 95%")
    elif ram >= 80:
        warnings.append(f"RAM usage {ram:.1f}% >= 80%")

    if disk >= 95:
        failed.append(f"Disk usage {disk:.1f}% >= 95%")
    elif disk >= 80:
        warnings.append(f"Disk usage {disk:.1f}% >= 80%")

    if load_1m > cores * 2:
        warnings.append(f"Load average {load_1m} > {cores * 2} ({cores} cores * 2.0)")

    for svc, state in (services or {}).items():
        if state != "active":
            failed.append(f"Service {svc} is {state}")

    if apache_http != 200:
        warnings.append(f"Apache HTTP {apache_http} on 8080")
    if nginx_http != 200:
        warnings.append(f"Nginx HTTP {nginx_http} on 80")
    if network != "reachable":
        failed.append(f"Network connectivity is {network}")

    overall = "CRITICAL" if failed else "WARNING" if warnings else "HEALTHY"
    return {
        "host": checks.get("host", "server1"),
        "timestamp": checks.get("timestamp", ""),
        "overall": overall,
        "warnings": warnings,
        "failed_checks": failed,
        "checks": checks,
    }


def main(argv=None):
    server = "server1"
    if argv and len(argv) > 1 and not argv[1].startswith("-"):
        server = argv[1]

    if os.environ.get("HEALTH_LOCAL_MODE") == "0":
        print(json.dumps({"error": "live mode disabled in this environment", "server": server}))
        raise SystemExit(0)

    checks = _random(server)
    evaluated = evaluate(checks)
    print(json.dumps({"overall": evaluated["overall"], "hosts": [evaluated]}, indent=2))


if __name__ == "__main__":
    main(sys.argv)
