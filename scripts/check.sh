#!/usr/bin/env bash
# Local verification harness for the API. Mirrors the CI backend job.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
PY="$API/.venv/bin"

export SOKOLA_DATABASE_URL="${SOKOLA_DATABASE_URL:-postgresql+psycopg://sokola:sokola@localhost:55432/sokola}"
export SOKOLA_ENVIRONMENT="${SOKOLA_ENVIRONMENT:-test}"
export SOKOLA_ALLOW_INSECURE_DEV_AUTH="true"

cd "$API"

echo "==> ruff"
"$PY/ruff" check app tests

echo "==> mypy"
"$PY/mypy" app

echo "==> architecture gate"
"$PY/python" -m scripts.check_architecture

echo "==> alembic upgrade head"
"$PY/alembic" upgrade head

echo "==> alembic check (models match migrations)"
"$PY/alembic" check

echo "==> pytest"
"$PY/pytest"

echo "==> OpenAPI parity"
"$PY/python" -m scripts.check_openapi_parity

echo "All backend checks passed."
