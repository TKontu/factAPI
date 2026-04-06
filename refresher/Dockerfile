FROM python:3.12-alpine

# busybox crond is pre-installed in Alpine — no apk add needed.

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fetch_rates.py .
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

# Install crontab for the root user
COPY crontab /etc/crontabs/root

CMD ["/app/entrypoint.sh"]
