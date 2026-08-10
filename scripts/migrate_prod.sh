#!/bin/bash
# Canonical production database migration entrypoint.
# This script is intentionally explicit: it never creates or resets users.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${DASHBOARD_COMPOSE_FILE:-$PROJECT_ROOT/docker-compose.prod.yml}"
ENV_FILE="${DASHBOARD_ENV_FILE:-$PROJECT_ROOT/.env.production}"

[[ -f "$COMPOSE_FILE" ]] || { echo "[ERROR] compose file is missing: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "[ERROR] production env file is missing: $ENV_FILE" >&2; exit 1; }

compose_run() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile full \
        run --rm --no-deps --entrypoint /opt/venv/bin/python backend "$@"
}

echo "[MIGRATE] Initializing/upgrading schema without user creation"
compose_run scripts/init_db.py --no-users

echo "[MIGRATE] Applying explicit MySQL compatibility migration"
compose_run scripts/migrate_mysql_schema.py

echo "[MIGRATE] Applying Phase A task/lease/outbox migration"
compose_run scripts/migrate_phase_a.py

echo "[MIGRATE] Production database migration completed"
