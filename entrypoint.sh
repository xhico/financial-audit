#!/bin/sh
set -e
python manage.py migrate --noinput
if [ "$1" = "gunicorn" ]; then
    python manage.py collectstatic --noinput
fi
exec "$@"
