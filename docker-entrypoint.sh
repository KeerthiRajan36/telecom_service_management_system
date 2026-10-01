#!/bin/sh
# Applies database migrations and seeds the first admin, then starts the server.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations..."
    attempt=1
    until alembic upgrade head; do
        if [ "$attempt" -ge 30 ]; then
            echo "Database still unavailable after $attempt attempts, giving up." >&2
            exit 1
        fi
        echo "Database not ready (attempt $attempt/30), retrying in 2s..."
        attempt=$((attempt + 1))
        sleep 2
    done
    python -m scripts.seed
fi

# Plain `uvicorn` does not read WEB_CONCURRENCY on its own (that's a Gunicorn convention) -
# honor it here for the default CMD so it's not a silently-ignored setting.
if [ "$1" = "uvicorn" ] && [ -n "$WEB_CONCURRENCY" ]; then
    set -- "$@" --workers "$WEB_CONCURRENCY"
fi

exec "$@"
