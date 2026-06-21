#!/bin/sh
# Refresh collected static files into the mounted volume on every container
# start. Docker named volumes are only seeded once (on first creation), so any
# static asset added after the first deploy — e.g. the site logo — never reaches
# the nginx-served volume unless we re-run collectstatic at runtime.
python manage.py collectstatic --noinput \
    || echo "[entrypoint] collectstatic failed — continuing with existing static files"

exec "$@"
