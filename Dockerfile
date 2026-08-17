FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitoring/ monitoring/

# default to JSON API; Telegram requires TELEGRAM_BOT_TOKEN
CMD ["python", "monitoring/api.py", "health", "--server", "server1"]
