#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

ok() { echo "OK  $1"; }
fail() { echo "FAIL $1: $2"; exit 1; }

test -f monitoring/local_health.py || fail "local_health.py" "missing"
test -f monitoring/telegram_bot.py || fail "telegram_bot.py" "missing"

# Local health returns valid JSON with overall + host keys.
HEALTH_JSON=$(python3 monitoring/local_health.py server1)
echo "$HEALTH_JSON" | python3 -c 'import sys,json; d=json.load(sys.stdin)' >/dev/null || fail "local_health.json" "invalid json"
echo "$HEALTH_JSON" | grep -q '"overall"' || fail "local_health.json" "missing overall"
echo "$HEALTH_JSON" | grep -q '"hosts"' || fail "local_health.json" "missing hosts"
echo "$HEALTH_JSON" | grep -q '"server1"' || fail "local_health.json" "missing server1"

# Telegram bot CLI commands produce readable output without a real token.
HEALTH_OUT=$(TELEGRAM_BOT_TOKEN=dummy python3 monitoring/telegram_bot.py --mode cli --text "/health server1") || fail "bot_cli_health" "command failed"
echo "$HEALTH_OUT" | grep -qi "Health Report" || fail "bot_cli_health" "missing header"

STATUS_OUT=$(TELEGRAM_BOT_TOKEN=dummy python3 monitoring/telegram_bot.py --mode cli --text "/status") || fail "bot_cli_status" "command failed"
echo "$STATUS_OUT" | grep -qi "status:" || fail "bot_cli_status" "missing status prefix"

HELP_OUT=$(TELEGRAM_BOT_TOKEN=dummy python3 monitoring/telegram_bot.py --mode cli --text "/help") || fail "bot_cli_help" "command failed"
echo "$HELP_OUT" | grep -qi "/health" || fail "bot_cli_help" "missing /help docs"

# Token handling failure path is explicit.
if TELEGRAM_BOT_TOKEN="" python3 monitoring/telegram_bot.py --mode cli --text "/health" 2>/dev/null; then
  fail "bot_missing_token" "expected nonzero exit"
fi

ok "phase1_verification"
