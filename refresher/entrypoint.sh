#!/bin/sh
set -e

# Alpine's busybox crond does NOT inherit Docker environment variables.
# Write REFRESHER_* vars to a file that the crontab sources before each job.
env | grep '^REFRESHER_' > /etc/refresher.env || true

# Seed historical data on container start (idempotent — skips if already exists).
python /app/fetch_rates.py --seed

# Hand off to crond in foreground so Docker keeps the container alive.
# -f  = foreground (don't daemonize)
# -l 2 = log all job executions
# -L /dev/stdout = send crond daemon logs to Docker log stream
exec crond -f -l 2 -L /dev/stdout
