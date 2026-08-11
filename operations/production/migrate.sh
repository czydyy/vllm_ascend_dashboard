#!/bin/bash
# Canonical production database migration entrypoint.
# This script is intentionally explicit: it never creates or resets users.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="${DASHBOARD_COMPOSE_FILE:-$PROJECT_ROOT/docker-compose.prod.yml}"
ENV_FILE="${DASHBOARD_ENV_FILE:-$PROJECT_ROOT/.env.production}"

[[ -f "$COMPOSE_FILE" ]] || { echo "[ERROR] compose file is missing: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "[ERROR] production env file is missing: $ENV_FILE" >&2; exit 1; }

compose_run() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile full \
        run --rm --no-deps --entrypoint /opt/venv/bin/python backend "$@"
}

echo "[MIGRATE] Running canonical MySQL migration"
compose_run scripts/migrate.py

echo "[MIGRATE] Production database migration completed"
