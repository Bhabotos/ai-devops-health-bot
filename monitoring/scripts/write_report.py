#!/usr/bin/env python3
"""Remote helper: write health report JSON to stdout for Ansible."""
import json
import os
import subprocess
import sys

def run(cmd, shell=False):
    r = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode

cpu_out, _ = run(["python3", "-c", "import os; stat=open('/proc/stat').readline().split(); idle=int(stat[4]); total=sum(map(int,stat[1:])); print(f'{(1-idle/total)*100:.1f}' if total>0 else '0')"])
ram_out, _ = run(["python3", "-c", "import os; m=open('/proc/meminfo').read(); total=int([l for l in m.splitlines() if 'MemTotal' in l][0].split()[1]); avail=int([l for l in m.splitlines() if 'MemAvailable' in l][0].split()[1]); print(f'{(1-avail/total)*100:.1f}')"])
disk_out, _ = run("sh -c 'df -P / | tail -1 | awk \"{print $5}\" | tr -d \"%\"'", shell=True)
load_out, _ = run("cat /proc/loadavg", shell=True)
uptime_out, _ = run("cat /proc/uptime", shell=True)
apache_out, apache_rc = run("systemctl is-active apache2", shell=True)
nginx_out, nginx_rc = run("systemctl is-active nginx", shell=True)
ssh_out, ssh_rc = run("systemctl is-active ssh", shell=True)
tcp_out, _ = run("ss -ltnp", shell=True)
gw_out, _ = run("ip route | grep default | awk '{print $3}'", shell=True)
net_cmd = f"ping -c 1 -W 2 {gw_out}" if gw_out else "ping -c 1 -W 2 127.0.0.1"
net_out, net_rc = run(net_cmd, shell=True)
apache_http_out, apache_http_rc = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080", shell=True)
nginx_http_out, nginx_http_rc = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80", shell=True)

load_parts = load_out.split()
uptime_parts = uptime_out.split()
tcp_lines = [line.strip() for line in tcp_out.splitlines() if line.strip()]
hostname_out, _ = run("hostname", shell=True)

report = {
    "host": hostname_out,
    "timestamp": subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip(),
    "checks": {
        "cpu_usage_percent": float(cpu_out),
        "ram_usage_percent": float(ram_out),
        "disk_usage_percent": float(disk_out),
        "load_avg": {
            "1m": float(load_parts[0]) if load_parts else 0.0,
            "5m": float(load_parts[1]) if len(load_parts) > 1 else 0.0,
            "15m": float(load_parts[2]) if len(load_parts) > 2 else 0.0,
            "cores": int(subprocess.check_output(["nproc"], text=True).strip()),
        },
        "uptime_seconds": float(uptime_parts[0]) if uptime_parts else 0.0,
        "services": {
            "apache2": apache_out if apache_rc == 0 else "unknown",
            "nginx": nginx_out if nginx_rc == 0 else "unknown",
            "ssh": ssh_out if ssh_rc == 0 else "unknown",
        },
        "tcp_ports": tcp_lines,
        "network": "reachable" if net_rc == 0 else "unreachable",
        "http_apache_8080": int(apache_http_out) if apache_http_rc == 0 and apache_http_out.isdigit() else 0,
        "http_nginx_80": int(nginx_http_out) if nginx_http_rc == 0 and nginx_http_out.isdigit() else 0,
    },
}

print(json.dumps(report, indent=2))
