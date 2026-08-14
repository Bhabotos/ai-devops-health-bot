# Telegram Integration

This directory is reserved for future Telegram bot integration.

## Planned capabilities

- Send `/health` command to a Telegram bot
- Receive structured health check JSON in Telegram
- Receive alert notifications for CRITICAL/WARNING status
- Configure target server and chat via `config.yaml` or environment variables

## Implementation notes

- Use a polling or webhook-based Telegram bot (python-telegram-bot or aiogram)
- The bot will invoke `run_health.py` on demand or on a schedule
- Output JSON will be formatted for Telegram delivery
- Authentication via bot token stored in `.env` or environment variables

## Not implemented yet

This directory is a placeholder. No Telegram integration code exists yet.
