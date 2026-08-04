#!/bin/sh
set -eu

max_attempts="${DATABASE_STARTUP_MAX_ATTEMPTS:-30}"
attempt=1

while ! python -m alembic -c /app/alembic.ini upgrade head; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Database migration failed after ${attempt} attempts." >&2
        exit 1
    fi

    echo "Database is not ready; retrying migration (${attempt}/${max_attempts})..." >&2
    attempt=$((attempt + 1))
    sleep 2
done

if [ "${1:-}" = "serve" ]; then
    set -- python -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers "${API_WORKERS:-2}" \
        --proxy-headers \
        "--forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-*}"
fi

exec "$@"
