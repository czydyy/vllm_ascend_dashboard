#!/bin/bash
# Safe production deployment for Docker Compose + MySQL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MIGRATE_SCRIPT="$SCRIPT_DIR/migrate.sh"
COMPOSE_FILE="${DASHBOARD_COMPOSE_FILE:-$PROJECT_ROOT/deploy/compose/production/compose.yml}"
ENV_FILE="${DASHBOARD_ENV_FILE:-$PROJECT_ROOT/.env.production}"
BACKUP_DIR="${DASHBOARD_BACKUP_DIR:-$PROJECT_ROOT/backups}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
MAX_WAIT=120
DO_PULL=true
DRY_RUN=false
FORCE_ROLLBACK=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pull) DO_PULL=false; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --rollback) FORCE_ROLLBACK=true; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

step() { echo; echo "=== $1 ==="; }
ok() { echo "[OK] $1"; }
warn() { echo "[WARN] $1"; }
die() { echo "[ERROR] $1" >&2; exit 1; }
compose() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile full "$@"; }
service_container() { compose ps -q "$1"; }
service_image() {
    local container
    container="$(service_container "$1")"
    [[ -n "$container" ]] || return 1
    docker inspect --format '{{.Config.Image}}' "$container"
}
mysql_root() {
    compose exec -T mysql sh -c \
        'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -N -e "$1"' sh "$1"
}
get_user_count() { mysql_root 'SELECT COUNT(*) FROM users'; }
get_table_count() { mysql_root 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()'; }
get_user_list() { mysql_root 'SELECT id, username, role FROM users ORDER BY id'; }

wait_for_health() {
    local elapsed=0
    while (( elapsed < MAX_WAIT )); do
        local backend_container
        backend_container="$(service_container backend)"
        if curl -fsS "http://127.0.0.1:${FRONTEND_PORT}/health" >/dev/null 2>&1 \
            && [[ -n "$backend_container" ]] \
            && docker inspect --format '{{.State.Health.Status}}' "$backend_container" 2>/dev/null | grep -q '^healthy$'; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

restore_database() {
    local backup_file="$1"
    [[ -s "$backup_file" ]] || die "restore backup is missing: $backup_file"
    compose exec -T mysql sh -c \
        'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS \`$1\`; CREATE DATABASE \`$1\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"' sh "$DATABASE_NAME"
    compose exec -T mysql sh -c \
        'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$1"' sh "$DATABASE_NAME" < "$backup_file"
}

rollback() {
    local backup_file="$1"
    step "ROLLBACK"
    compose stop scheduler collector backend frontend || true
    restore_database "$backup_file"
    DASHBOARD_BACKEND_IMAGE="$PRE_BACKEND_IMAGE" \
    DASHBOARD_FRONTEND_IMAGE="$PRE_FRONTEND_IMAGE" \
    DASHBOARD_LITELLM_IMAGE="$PRE_LITELLM_IMAGE" \
        compose up -d mysql litellm backend frontend scheduler collector
    wait_for_health || die "rollback completed but services are unhealthy"
    ok "rollback restored database and previous images; users=$(get_user_count)"
}

command -v docker >/dev/null 2>&1 || die "docker is not installed"
[[ -f "$COMPOSE_FILE" ]] || die "compose file is missing: $COMPOSE_FILE"
[[ -f "$ENV_FILE" ]] || die "production environment file is missing: $ENV_FILE"
mysql_container="$(service_container mysql)"
[[ -n "$mysql_container" ]] || die "MySQL service is not running"
DATABASE_NAME="$(compose exec -T mysql sh -c 'printf %s "$MYSQL_DATABASE"')"
[[ "$DATABASE_NAME" =~ ^[a-zA-Z0-9_]+$ ]] || die "unsafe MySQL database name"

if $FORCE_ROLLBACK; then
    latest_backup="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'vllm_dashboard_*.sql' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
    [[ -n "$latest_backup" ]] || die "no MySQL backup is available"
    rollback "$latest_backup"
    exit 0
fi

if ! $DRY_RUN; then
    [[ -n "${DEPLOY_ADMIN_USERNAME:-}" && -n "${DEPLOY_ADMIN_PASSWORD:-}" ]] \
        || die "DEPLOY_ADMIN_USERNAME and DEPLOY_ADMIN_PASSWORD are required for login verification"
fi

step "1/9 Backup and restore verification"
backup_output="$(bash "$SCRIPT_DIR/backup.sh" --verify-restore 2>&1)" || die "backup failed: $backup_output"
backup_file="$(echo "$backup_output" | tail -1)"
[[ -s "$backup_file" && -s "$backup_file.meta" ]] || die "verified backup artifacts are missing"
grep -q '^restore_verified=true$' "$backup_file.meta" || die "backup restore verification did not pass"
ok "verified backup: $backup_file"

step "2/9 Record pre-deployment state"
pre_users="$(get_user_count)"
pre_tables="$(get_table_count)"
pre_git="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)"
PRE_BACKEND_IMAGE="$(service_image backend)" || die "backend image cannot be determined"
PRE_FRONTEND_IMAGE="$(service_image frontend)" || die "frontend image cannot be determined"
PRE_LITELLM_IMAGE="$(service_image litellm)" || die "LiteLLM image cannot be determined"
(( pre_users > 0 && pre_tables > 0 )) || die "invalid pre-deployment database state"
ok "commit=$pre_git users=$pre_users tables=$pre_tables"
get_user_list | sed 's/^/  /'

if $DRY_RUN; then
    ok "dry run complete; no code, schema, or service changes were made"
    exit 0
fi

step "3/9 Update source"
if $DO_PULL; then
    git -C "$PROJECT_ROOT" pull --ff-only origin main || die "git pull --ff-only failed"
else
    warn "source pull skipped"
fi
new_git="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)"
ok "$pre_git -> $new_git"

step "4/9 Pull immutable release images"
compose pull backend frontend litellm || die "image pull failed; running services were not changed"

step "5/9 Run explicit MySQL migration"
if ! bash "$MIGRATE_SCRIPT"; then
    warn "migration failed; restoring verified database backup"
    restore_database "$backup_file"
    die "migration failed and database was restored"
fi

post_migration_users="$(get_user_count)"
post_migration_tables="$(get_table_count)"
if (( post_migration_users < pre_users || post_migration_tables < pre_tables )); then
    restore_database "$backup_file"
    die "database counts decreased during migration; backup restored"
fi
ok "migration verified: users=$post_migration_users tables=$post_migration_tables"

step "6/9 Start updated containers"
if ! compose up -d mysql litellm backend frontend scheduler collector; then
    rollback "$backup_file"
    die "container startup failed; rollback completed"
fi

step "7/9 Health checks"
if ! wait_for_health; then
    rollback "$backup_file"
    die "services failed health checks; rollback completed"
fi
curl -fsS "http://127.0.0.1:${FRONTEND_PORT}/api/v1/daily-report/latest" >/dev/null 2>&1 \
    && warn "daily report endpoint unexpectedly allowed anonymous access" || true
ok "frontend and backend containers are healthy"

step "8/9 Login and database preservation"
login_payload="$(DEPLOY_ADMIN_USERNAME="$DEPLOY_ADMIN_USERNAME" DEPLOY_ADMIN_PASSWORD="$DEPLOY_ADMIN_PASSWORD" python3 -c 'import json,os; print(json.dumps({"username":os.environ["DEPLOY_ADMIN_USERNAME"],"password":os.environ["DEPLOY_ADMIN_PASSWORD"]}))')"
login_response="$(curl -fsS -X POST "http://127.0.0.1:${FRONTEND_PORT}/api/v1/auth/login" -H 'Content-Type: application/json' --data-binary "$login_payload")" \
    || { rollback "$backup_file"; die "admin login failed; rollback completed"; }
echo "$login_response" | grep -q 'access_token' \
    || { rollback "$backup_file"; die "admin login response is invalid; rollback completed"; }
post_users="$(get_user_count)"
post_tables="$(get_table_count)"
if (( post_users < pre_users || post_tables < pre_tables )); then
    rollback "$backup_file"
    die "post-deployment database counts decreased; rollback completed"
fi
ok "login passed; users=$pre_users->$post_users tables=$pre_tables->$post_tables"
get_user_list | sed 's/^/  /'

step "9/9 Complete"
ok "deployment complete: $pre_git -> $new_git"
ok "verified backup retained at: $backup_file"
