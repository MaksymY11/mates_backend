#!/bin/sh
set -e

if [ -n "$FIREBASE_SERVICE_ACCOUNT_JSON" ]; then
    echo "$FIREBASE_SERVICE_ACCOUNT_JSON" > /app/firebase-service-account.json
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000