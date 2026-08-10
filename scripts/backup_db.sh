#!/bin/bash
# Online MySQL backup for the production Docker deployment.
# Phase 0 升级：三库备份 + --source-data=2 + GTID/binlog 位置记录。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# 自动加载 .env.production 中的 MYSQL_ROOT_PASSWORD 等
if [[ -f "$PROJECT_ROOT/.env.production" ]]; then
    set -a
    source "$PROJECT_ROOT/.env.production"
    set +a
fi
BACKUP_DIR="${DASHBOARD_BACKUP_DIR:-$PROJECT_ROOT/backups}"
MYSQL_CONTAINER="${DASHBOARD_MYSQL_CONTAINER:-vllm-dashboard-mysql}"
RETENTION_DAYS=30
SILENT=false
VERIFY_RESTORE=false

# 默认备份全部三个逻辑库；拆分前只有一个 vllm_dashboard 时自动回退。
DATABASES="${DASHBOARD_BACKUP_DATABASES:-control_db collection_db telemetry_db}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --silent) SILENT=true; shift ;;
        --verify-restore) VERIFY_RESTORE=true; shift ;;
        --retention) RETENTION_DAYS="${2:?retention days required}"; shift 2 ;;
        --databases) DATABASES="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

log() { $SILENT || echo "[BACKUP] $1"; }
die() { echo "[ERROR] $1" >&2; exit 1; }

mysql_root_exec() {
    docker exec "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "$1"
}

command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker inspect "$MYSQL_CONTAINER" >/dev/null 2>&1 || die "MySQL container is unavailable: $MYSQL_CONTAINER"
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || die "retention must be a non-negative integer"

# 检测实际存在的数据库
EXISTING_DBS=""
for db in $DATABASES; do
    [[ "$db" =~ ^[a-zA-Z0-9_]+$ ]] || die "unsafe database name: $db"
    if mysql_root_exec "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$db'" 2>/dev/null | grep -q 1; then
        EXISTING_DBS="$EXISTING_DBS $db"
    fi
done

# 如果三个逻辑库都不存在，回退到 MySQL 容器的默认数据库
if [[ -z "${EXISTING_DBS// /}" ]]; then
    # 回退到 vllm_dashboard（Phase 0 拆分前单库名）
    default_db="vllm_dashboard"
    if mysql_root_exec "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$default_db'" 2>/dev/null | grep -q 1; then
        EXISTING_DBS="$default_db"
    fi
fi

[[ -n "${EXISTING_DBS// /}" ]] || die "no backup target databases found (tried: $DATABASES and MYSQL_DATABASE)"

log "backup targets: $EXISTING_DBS"

mkdir -p "$BACKUP_DIR"
timestamp="$(date +%Y%m%d_%H%M%S)"
backup_file="$BACKUP_DIR/vllm_dashboard_${timestamp}.sql"
metadata_file="$backup_file.meta"

# 记录备份前状态
pre_users=0
pre_tables_total=0
for db in $EXISTING_DBS; do
    count="$(mysql_root_exec "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$db'" 2>/dev/null || echo 0)"
    pre_tables_total=$((pre_tables_total + count))
    if mysql_root_exec "SELECT 1 FROM information_schema.tables WHERE table_schema='$db' AND table_name='users'" 2>/dev/null | grep -q 1; then
        users="$(mysql_root_exec "SELECT COUNT(*) FROM \`$db\`.users" 2>/dev/null || echo 0)"
        [[ "$users" =~ ^[0-9]+$ ]] || die "live database user count is invalid for $db: $users"
        pre_users=$((pre_users + users))
    fi
done
[[ "$pre_users" =~ ^[0-9]+$ ]] && (( pre_users > 0 )) || die "live database user count is invalid: $pre_users"
[[ "$pre_tables_total" -gt 0 ]] || die "live database table count is invalid: $pre_tables_total"

log "creating transaction-consistent MySQL dump for: $EXISTING_DBS"

# --source-data=2 将当时的 binlog 坐标写入 dump（注释形式），
# 使 PITR 恢复可以从备份位置继续应用 binlog。
# --no-tablespaces 避免需要 PROCESS 权限。
dump_cmd="mysqldump -uroot -p\"\$MYSQL_ROOT_PASSWORD\" \
  --databases $EXISTING_DBS \
  --single-transaction \
  --quick \
  --routines \
  --triggers \
  --events \
  --source-data=2 \
  --no-tablespaces"

if ! docker exec "$MYSQL_CONTAINER" sh -c "exec $dump_cmd" > "$backup_file"; then
    rm -f "$backup_file"
    die "mysqldump failed"
fi

[[ -s "$backup_file" ]] || die "backup is empty"
grep -q 'CREATE TABLE .users.' "$backup_file" || die "backup does not contain users table"
grep -q 'Dump completed on' "$backup_file" || die "mysqldump completion marker is missing"

# 提取 binlog 恢复坐标
binlog_file="$(grep -oP 'SOURCE_LOG_FILE='\''\K[^'\'']+' "$backup_file" 2>/dev/null || echo "")"
binlog_position="$(grep -oP 'SOURCE_LOG_POS=\K[0-9]+' "$backup_file" 2>/dev/null || echo "")"

backup_users="$pre_users"
backup_tables="$pre_tables_total"

# 恢复校验：将备份恢复到隔离的验证库
if $VERIFY_RESTORE; then
    verify_db="vllm_dashboard_verify_${timestamp}"
    [[ "$verify_db" =~ ^[a-zA-Z0-9_]+$ ]] || die "unsafe verification database name"
    cleanup_verify() {
        docker exec "$MYSQL_CONTAINER" sh -c \
            'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS \`$1\`"' sh "$verify_db" \
            >/dev/null 2>&1 || true
    }
    trap cleanup_verify EXIT

    docker exec "$MYSQL_CONTAINER" sh -c \
        'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE \`$1\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"' sh "$verify_db"
    # 去掉 GTID_PURGED 语句（verify 用独立临时库，不需要 GTID）
    sed '/^SET @@GLOBAL.GTID_PURGED=/d' "$backup_file" | \
    docker exec -i "$MYSQL_CONTAINER" sh -c \
        'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$1"' sh "$verify_db"

    # 验证用户数和表数
    backup_users=0
    backup_tables=0
    for db in $EXISTING_DBS; do
        db_users="$(docker exec "$MYSQL_CONTAINER" sh -c \
            'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$1" -N -e "SELECT COUNT(*) FROM users" 2>/dev/null || echo 0' sh "$db")"
        db_tables="$(docker exec "$MYSQL_CONTAINER" sh -c \
            'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$1" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"'$db'\"" 2>/dev/null || echo 0' sh "$verify_db")"
        backup_users=$((backup_users + db_users))
        backup_tables=$((backup_tables + db_tables))
    done

    [[ "$backup_users" = "$pre_users" ]] || die "restore verification user count mismatch: $pre_users -> $backup_users"
    [[ "$backup_tables" = "$pre_tables_total" ]] || die "restore verification table count mismatch: $pre_tables_total -> $backup_tables"
    cleanup_verify
    trap - EXIT
fi

checksum="$(sha256sum "$backup_file" | awk '{print $1}')"
git_commit="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"

{
    echo "created_at=$(date --iso-8601=seconds)"
    echo "git_commit=$git_commit"
    echo "sha256=$checksum"
    echo "users=$backup_users"
    echo "tables=$backup_tables"
    echo "restore_verified=$VERIFY_RESTORE"
    echo "binlog_file=${binlog_file:-unknown}"
    echo "binlog_position=${binlog_position:-unknown}"
    echo "backup_time=$(date --iso-8601=seconds)"
} > "$metadata_file"

# 清理过期备份
find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'vllm_dashboard_*.sql' -o -name 'vllm_dashboard_*.sql.meta' \) \
    -mtime "+$RETENTION_DAYS" -delete

log "backup verified: users=$backup_users tables=$backup_tables sha256=$checksum"
log "binlog: ${binlog_file:-unknown}:${binlog_position:-unknown}"
echo "$backup_file"
