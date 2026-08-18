# Ansible Web Deployment with Telegram Health Bot

A lightweight automation project that deploys Apache behind Nginx on `server1` using Ansible, then exposes live health status through a Telegram bot.

## What this does

- Deploys Apache on `127.0.0.1:8080` and Nginx as a reverse proxy on port `80`.
- Runs read-only health checks via ad-hoc Ansible commands.
- Sends formatted health reports to Telegram on demand.

## Architecture

```text
Telegram
   |
   v
Telegram Bot (telegram/bot.py)
   |
   | runs ./health
   v
Health Runner (monitoring/run_health.py)
   |
   | ansible -i inventory.ini server1 -b -m shell ...
   v
server1
   |
   | returns JSON
   v
Health JSON
   |
   | parsed and formatted
   v
Telegram
```

### Flow

1. `/start` or `/health` from Telegram triggers the bot.
2. The bot executes the `./health` runner.
3. The runner uses Ansible against `inventory.ini` to gather CPU, RAM, disk, load, services, HTTP status, and network reachability.
4. Results are returned as JSON.
5. The bot formats the JSON into a readable Telegram message.

## Prerequisites

- Linux host with Python 3.8+
- Ansible installed and available in PATH
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- SSH access to `server1` from the machine running this project
- Dependencies installed in a virtual environment:
  - `python-dotenv`
  - `requests`
  - `python-telegram-bot`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure `inventory.ini` for your target host.

Create `telegram/.env` with your Telegram bot token:

```bash
echo "TELEGRAM_BOT_TOKEN=REPLACE_WITH_YOUR_TOKEN" > telegram/.env
chmod 600 telegram/.env
```

Keep `telegram/.env` private. It is ignored by Git.

## Run

Activate the virtual environment, then start the bot:

```bash
source .venv/bin/activate
python telegram/bot.py
```

## Test from Telegram

Once the bot is running, send these commands from any Telegram client:

- `/start`
- `/health`
- `/health server1`

`/health server1` executes the health runner and returns the live report.

## Security notes

- Never commit `telegram/.env`, `.venv/`, or backup files.
- The bot loads the token at runtime from `telegram/.env`.
- Sensitive strings are redacted in bot logs.

## CI/CD

- `docker` job builds the image locally and verifies API behavior inside the container.
- On push to `main`, the workflow also tags and pushes to Docker Hub using GitHub Secrets.
- Deployment stays disabled until you explicitly enable the `deploy` job.

### Required secrets

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Image push to Docker Hub is skipped automatically if either secret is missing, so PR builds on forks remain green.
