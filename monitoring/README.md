# Monitoring

Read-only AI DevOps health monitoring for the `ansible-web-deployment` project.

## Contents

- `config.yaml` — threshold configuration for health evaluation
- `health.yml` — Ansible playbook that performs read-only checks against `inventory.ini`
- `run_health.py` — local runner that executes the playbook and emits structured JSON
- `health` — local `/health` entry-point script

## Usage

From the project root:

```bash
./health
```

Or directly:

```bash
python3 monitoring/run_health.py
```

Output is structured JSON suitable for AI agent parsing.

## Requirements

- Python 3.8+
- Ansible core
- SSH access to hosts in `inventory.ini`

## Design

- Health checks are strictly read-only.
- No service restarts, installs, removals, or reconfigurations.
- Reports are fetched to `monitoring/reports/` for local inspection.
- Future Telegram integration lives under `monitoring/telegram/`.
