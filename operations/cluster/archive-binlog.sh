#!/bin/bash
# Binlog 异地归档脚本
# 每 4 小时执行一次，归档目标 RPO ≤ 4 小时。
# cron: 0 */4 * * * bash /root/vllm_ascend_dashboard/operations/cluster/archive-binlog.sh
set -euo pipefail

ARCHIVE_HOST="${ARCHIVE_HOST:-node-a}"
ARCHIVE_PATH="${ARCHIVE_PATH:-/data/binlog-archive}"
BINLOG_DIR="${BINLOG_DIR:-/data/mysql/binlog}"  # 宿主机 bind mount 路径
MYSQL_CONTAINER="${MYSQL_CONTAINER:-vllm-dashboard-mysql}"
LOG_FILE="${LOG_FILE:-/var/log/binlog_archive.log}"

log() { echo "$(date --iso-8601=seconds) [ARCHIVE] $1" | tee -a "$LOG_FILE"; }
die() { log "ERROR: $1"; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker inspect "$MYSQL_CONTAINER" >/dev/null 2>&1 || die "MySQL container is unavailable: $MYSQL_CONTAINER"
[[ -d "$BINLOG_DIR" ]] || die "binlog directory does not exist: $BINLOG_DIR"

# 1. 关闭当前 binlog 文件，开始新文件
mysql -e "FLUSH BINARY LOGS;" 2>/dev/null || \
  docker exec "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "FLUSH BINARY LOGS;"

# 2. 获取当前正在写入的 binlog 文件
CURRENT_BINLOG=$(docker exec "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N \
  -e "SHOW MASTER STATUS" 2>/dev/null | awk '{print $1}')

if [[ -z "$CURRENT_BINLOG" ]]; then
    log "WARNING: could not determine current binlog file, archiving all available"
    CURRENT_BINLOG="__none__"
fi

# 3. 归档已完成（非当前写入中）的 binlog 文件
archive_failed=0
archive_count=0
checksum_file="$BINLOG_DIR/archive_checksums.log"

for f in "$BINLOG_DIR"/mysql-bin.[0-9]*; do
    [[ -f "$f" ]] || continue
    basename=$(basename "$f")
    [[ "$basename" == "$CURRENT_BINLOG" ]] && continue

    # 记录 SHA256
    sha256sum "$f" >> "$checksum_file"

    # rsync 到异地
    if rsync -az "$f" "$ARCHIVE_HOST:$ARCHIVE_PATH/$(date +%Y%m%d)/"; then
        archive_count=$((archive_count + 1))
    else
        archive_failed=1
        log "FAILED: rsync $basename"
    fi
done

# 4. 归档完整性检查
if [[ "$archive_failed" -ne 0 ]]; then
    die "archive failed for $archive_failed file(s); $archive_count succeeded"
fi

# 5. 清理过期归档（保留 30 天）
ssh "$ARCHIVE_HOST" "find '$ARCHIVE_PATH' -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;" 2>/dev/null || true

log "archive complete: $archive_count file(s) to $ARCHIVE_HOST:$ARCHIVE_PATH/$(date +%Y%m%d)"
