# Monitoring

Read-only AI DevOps health monitoring, triage, safe actions, and observability for the `ansible-web-deployment` project.

## Contents

- `config.yaml` — threshold configuration for health evaluation
- `run_health.py` — Ansible-based live health runner
- `local_health.py` — local offline fallback health generator for testing
- `triage.py` — Phase 2 triage brain: summaries, risk levels, history, trends
- `actions.py` — Phase 3 safe action gateway: allowlist, confirm/cancel, audit log
- `observability.py` — Phase 4 observability: combined logs, export, retention
- `telegram_bot.py` — Phase 1/2/3/4 Telegram bot skeleton with read-only and approved-action commands
- `telegram/README.md` — Telegram integration notes
- `health` — local `/health` entry-point script
- `reports/reports_index.json` — local health history log
- `reports/actions_index.json` — local action audit log

## Usage

From the project root:

```bash
./health
python3 monitoring/local_health.py
python3 monitoring/telegram_bot.py --mode cli --text "/health"
python3 monitoring/telegram_bot.py --mode cli --text "/status"
python3 monitoring/telegram_bot.py --mode cli --text "/history 5"
python3 monitoring/telegram_bot.py --mode cli --text "/logs 5"
python3 monitoring/telegram_bot.py --mode cli --text "/actions"
python3 monitoring/telegram_bot.py --mode cli --text "/do restart_nginx server1"
python3 monitoring/telegram_bot.py --mode cli --text "/confirm restart_nginx server1"
python3 monitoring/telegram_bot.py --mode cli --text "/audit 5"
python3 monitoring/telegram_bot.py --mode cli --text "/export"
python3 monitoring/telegram_bot.py --mode cli --text "/retention"
```

Output is structured JSON suitable for AI agent parsing.

## Telegram Commands

- `/health [server]` — full health report
- `/status [server]` — triage summary with risk level and suggested checks
- `/history [n]` — recent health history, default 10
- `/logs [n]` — recent combined health/action logs, default 20
- `/actions` — list approved actions
- `/do <action> [server]` — request an action
- `/confirm <action> [server]` — confirm pending action
- `/cancel <action> [server]` — cancel pending action
- `/audit [n]` — recent action history, default 10
- `/export` — JSON snapshot to `monitoring/reports/snapshot.json`
- `/retention` — prune old logs, keep last 100 entries
- `/help` — command reference
- `/start` — welcome and usage

## Requirements

- Python 3.8+
- Ansible core
- SSH access to hosts in `inventory.ini`
- Telegram bot token from [@BotFather](https://t.me/BotFather)

## Design

- Health checks are strictly read-only.
- No service restarts, installs, removals, or reconfigurations from health collection.
- Approved actions are limited to a small allowlist and require explicit confirm/cancel flow.
- Phase 1/2/3/4 bot commands are CLI-verifiable without real Telegram network calls.
- Mock execution is used for offline verification; real execution is not wired yet.
