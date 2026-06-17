#!/bin/sh
# Refresh collected static files into the mounted volume on every container
# start. Docker named volumes are only seeded once (on first creation), so any
# static asset added after the first deploy — e.g. the site logo — never reaches
# the nginx-served volume unless we re-run collectstatic at runtime.
python manage.py collectstatic --noinput \
    || echo "[entrypoint] collectstatic failed — continuing with existing static files"

# Schedule the unconfirmed-order cleanup cron (every 5 minutes).
# Cancels orders stuck in pending_confirmation and restores their stock.
(while true; do
    python manage.py cancel_unconfirmed_orders --dry-run false \
        >> /tmp/cancel_unconfirmed.log 2>&1
    sleep 300
done) &

exec "$@"
