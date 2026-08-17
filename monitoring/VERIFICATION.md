# Verification Checklist

Use this checklist to verify the AI DevOps Command Center locally and in Docker.

## Prerequisites

- Python 3.8+
- virtual environment at `.venv/`
- dependencies from `requirements.txt`
- optional: Docker and Docker Compose

## Local verification

1. Install dependencies:
   ```bash
   .venv/bin/python -m pip install -r requirements.txt
   ```
2. Run unit tests:
   ```bash
   .venv/bin/python -m unittest discover -s tests -v
   ```
3. Run canonical verification:
   ```bash
   hermes verify --json
   ```
4. Manual CLI smoke checks:
   ```bash
   python3 monitoring/telegram_bot.py --mode cli --token dummy --text "/help"
   python3 monitoring/telegram_bot.py --mode cli --token dummy --text "/health"
   python3 monitoring/telegram_bot.py --mode cli --token dummy --text "/status"
   python3 monitoring/telegram_bot.py --mode cli --token dummy --text "/actions"
   python3 monitoring/telegram_bot.py --mode cli --token dummy --text "/logs 5"
   python3 monitoring/telegram_bot.py --mode cli --token dummy --text "/export"
   python3 monitoring/telegram_bot.py --mode cli --text "/do show_logs server1"
   python3 monitoring/telegram_bot.py --mode cli --text "/confirm show_logs server1"
   python3 monitoring/telegram_bot.py --mode cli --text "/audit 5"
   python3 monitoring/api.py health --server server1
   python3 monitoring/api.py export
   python3 monitoring/api.py retention --keep 20
   ```

## Docker verification

1. Build image:
   ```bash
   docker build -t ai-devops-command-center:phase5 .
   ```
2. Start service:
   ```bash
   docker compose up --build
   ```
3. Verify container health:
   ```bash
   docker compose ps
   ```
4. Verify reports volume:
   ```bash
   ls monitoring/reports
   ```
5. Run API inside container:
   ```bash
   docker compose exec command-center python monitoring/api.py allowlist
   ```

## Production notes

- Telegram requires `TELEGRAM_BOT_TOKEN` in the container env or `.env` with Compose.
- Set `HEALTH_BOT_LOG_LEVEL=INFO` or `DEBUG`.
- Mount `./monitoring/reports` to persist history across restarts.
- Keep container time synchronized with the monitoring host for consistent timestamps.
