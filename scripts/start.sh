#!/bin/bash
set -e

echo "=== Alembic migration check ==="

if [ "${RESET_DATABASE_ON_DEPLOY:-0}" = "1" ]; then
    echo "RESET_DATABASE_ON_DEPLOY=1 detected."
    echo "Dropping and recreating the public schema before migrations."
    python -m scripts.reset_database_schema
fi

if ! CURRENT=$(alembic current 2>&1); then
    echo "Alembic current failed. Refusing to continue:"
    echo "$CURRENT"
    exit 1
fi
echo "Alembic current output:"
echo "$CURRENT"

# Empty databases migrate from base. Existing unversioned schemas are reconciled
# before upgrade so Alembic does not try to recreate tables that already exist.
if echo "$CURRENT" | grep -qE "^[0-9a-f]|[0-9]{4}_"; then
    echo "Revision found in DB — running upgrade head normally."
else
    echo "No revision ID detected. Checking for existing unversioned schema."
    python -m scripts.recover_unversioned_schema
fi

echo "=== Running alembic upgrade head ==="
alembic upgrade head
echo "Migrations OK."

echo "=== Starting uvicorn ==="
export PYTHONUNBUFFERED=1
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
