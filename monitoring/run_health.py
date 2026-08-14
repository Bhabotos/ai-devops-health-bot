#!/usr/bin/env python3
"""Run read-only health checks against webservers using direct ad-hoc Ansible commands."""

import json
import subprocess
import sys
from pathlib import Path

MONITORING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MONITORING_DIR.parent
INVENTORY = PROJECT_ROOT / "inventory.ini"
CONFIG = MONITORING_DIR / "config.yaml"
HOST = "server1"


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def adhoc(module, args):
    """Run ad-hoc Ansible command and extract stdout after ' >> '."""
    result = run([
        "ansible",
        "-i", str(INVENTORY),
        HOST,
        "-b",
        "-m", module,
        "-a", args,
    ])
    marker = " >>"
    if marker in result.stdout:
        after = result.stdout.split(marker, 1)[1]
        if after.startswith(" "):
            after = after[1:]
        return after.strip()
    return result.stdout.strip()


def load_config():
    try:
        import yaml
        with open(CONFIG) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def gather():
    checks = {}
    checks["host"] = HOST
    checks["timestamp"] = run([
        "date", "-u", "+%Y-%m-%dT%H:%M:%SZ"
    ]).stdout.strip()

    checks["cpu_usage_percent"] = float(adhoc(
        "shell",
        "python3 -c \"import os; stat=open('/proc/stat').readline().split(); idle=int(stat[4]); total=sum(map(int,stat[1:])); print(f'{(1-idle/total)*100:.1f}' if total>0 else '0')\""
    ))
    checks["ram_usage_percent"] = float(adhoc(
        "shell",
        "python3 -c \"import os; m=open('/proc/meminfo').read(); total=int([l for l in m.splitlines() if 'MemTotal' in l][0].split()[1]); avail=int([l for l in m.splitlines() if 'MemAvailable' in l][0].split()[1]); print(f'{(1-avail/total)*100:.1f}')\""
    ))
    checks["disk_usage_percent"] = float(adhoc(
        "shell",
        "df -P / | tail -1 | awk '{print $5}' | tr -d '%'"
    ))

    load_raw = adhoc("shell", "cat /proc/loadavg")
    load_parts = load_raw.split()
    checks["load_avg"] = {
        "1m": float(load_parts[0]) if load_parts else 0.0,
        "5m": float(load_parts[1]) if len(load_parts) > 1 else 0.0,
        "15m": float(load_parts[2]) if len(load_parts) > 2 else 0.0,
        "cores": int(run(["nproc"]).stdout.strip() or "1"),
    }

    uptime_raw = adhoc("shell", "cat /proc/uptime")
    checks["uptime_seconds"] = float(uptime_raw.split()[0]) if uptime_raw else 0.0

    checks["services"] = {
        "apache2": adhoc("shell", "systemctl is-active apache2"),
        "nginx": adhoc("shell", "systemctl is-active nginx"),
        "ssh": adhoc("shell", "systemctl is-active ssh"),
    }

    tcp_raw = adhoc("shell", "ss -ltnp")
    checks["tcp_ports"] = [line.strip() for line in tcp_raw.splitlines() if line.strip()]

    gw = adhoc("shell", "ip route | grep default | awk '{print $3}'")
    net_cmd = f"ping -c 1 -W 2 {gw}" if gw else "ping -c 1 -W 2 127.0.0.1"
    net_result = run([
        "ansible", "-i", str(INVENTORY), HOST, "-b",
        "-m", "shell", "-a", net_cmd
    ])
    if "1 received" in net_result.stdout:
        checks["network"] = "reachable"
    else:
        fallback_result = run([
            "ansible", "-i", str(INVENTORY), HOST, "-b",
            "-m", "shell", "-a", "ping -c 1 -W 2 127.0.0.1"
        ])
        checks["network"] = "reachable" if "1 received" in fallback_result.stdout else "unreachable"

    apache_http = adhoc(
        "shell",
        "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080"
    )
    nginx_http = adhoc(
        "shell",
        "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80"
    )

    try:
        checks["http_apache_8080"] = int(apache_http)
    except (TypeError, ValueError):
        checks["http_apache_8080"] = 0
    try:
        checks["http_nginx_80"] = int(nginx_http)
    except (TypeError, ValueError):
        checks["http_nginx_80"] = 0

    return checks


def evaluate(checks, config):
    thresholds = config.get("thresholds", {})
    cpu = float(checks.get("cpu_usage_percent", 0))
    ram = float(checks.get("ram_usage_percent", 0))
    disk = float(checks.get("disk_usage_percent", 0))
    load_avg = checks.get("load_avg", {})
    load_1m = float(load_avg.get("1m", 0))
    cores = int(load_avg.get("cores", 1))
    apache_http = int(checks.get("http_apache_8080", 0))
    nginx_http = int(checks.get("http_nginx_80", 0))
    services = checks.get("services", {})
    network = str(checks.get("network", "unknown"))

    warnings = []
    failed = []

    cpu_warn = float(thresholds.get("cpu", {}).get("warning", 80))
    cpu_crit = float(thresholds.get("cpu", {}).get("critical", 95))
    ram_warn = float(thresholds.get("ram", {}).get("warning", 80))
    ram_crit = float(thresholds.get("ram", {}).get("critical", 95))
    disk_warn = float(thresholds.get("disk", {}).get("warning", 80))
    disk_crit = float(thresholds.get("disk", {}).get("critical", 95))
    load_mult = float(thresholds.get("load_avg", {}).get("multiplier", 2.0))

    if cpu >= cpu_crit:
        failed.append(f"CPU usage {cpu:.1f}% >= {cpu_crit}%")
    elif cpu >= cpu_warn:
        warnings.append(f"CPU usage {cpu:.1f}% >= {cpu_warn}%")

    if ram >= ram_crit:
        failed.append(f"RAM usage {ram:.1f}% >= {ram_crit}%")
    elif ram >= ram_warn:
        warnings.append(f"RAM usage {ram:.1f}% >= {ram_warn}%")

    if disk >= disk_crit:
        failed.append(f"Disk usage {disk:.1f}% >= {disk_crit}%")
    elif disk >= disk_warn:
        warnings.append(f"Disk usage {disk:.1f}% >= {disk_warn}%")

    if load_1m > cores * load_mult:
        warnings.append(
            f"Load average {load_1m} > {cores * load_mult} ({cores} cores * {load_mult})"
        )

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
        "host": checks.get("host", HOST),
        "timestamp": checks.get("timestamp", ""),
        "overall": overall,
        "warnings": warnings,
        "failed_checks": failed,
        "checks": checks,
    }


def main():
    config = load_config()
    checks = gather()
    evaluated = evaluate(checks, config)
    output = {
        "overall": evaluated["overall"],
        "hosts": [evaluated],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
