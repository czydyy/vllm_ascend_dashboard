#!/bin/bash
# Step 0.4: Production health check script
# 检查: MySQL / Docker / 备份 / 磁盘 / 核心服务
# 用法: bash scripts/health_check.sh [--json]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
if [[ -f "$PROJECT_ROOT/.env.production" ]]; then
    set -a; source "$PROJECT_ROOT/.env.production"; set +a
fi

MYSQL_CONTAINER="${DASHBOARD_MYSQL_CONTAINER:-vllm-dashboard-mysql}"
BACKUP_DIR="${DASHBOARD_BACKUP_DIR:-$PROJECT_ROOT/backups}"
JSON=false; [[ "${1:-}" == "--json" ]] && JSON=true

mysql_exec() {
    docker exec "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "$1" 2>/dev/null || echo "ERR"
}

# ── System ──
DISK_USED_PCT=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
MEM_AVAIL_MB=$(free -m | awk 'NR==2 {print $7}')
LOAD=$(cat /proc/loadavg | awk '{print $1}')

# ── MySQL ──
MYSQL_UPTIME=$(docker inspect "$MYSQL_CONTAINER" --format '{{.State.Status}}' 2>/dev/null || echo "DOWN")
MYSQL_CONNS=$(mysql_exec "SELECT COUNT(*) FROM information_schema.PROCESSLIST" 2>/dev/null || echo "ERR")
BUFFER_HIT=$(mysql_exec "SELECT ROUND((1 - (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME='Innodb_buffer_pool_reads') / NULLIF((SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME='Innodb_buffer_pool_read_requests'),0)) * 100, 2)" 2>/dev/null || echo "ERR")
SLOW_QUERIES_1H=$(docker exec "$MYSQL_CONTAINER" sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM mysql.slow_log WHERE start_time > NOW() - INTERVAL 1 HOUR"' 2>/dev/null || echo "ERR")

# ── Docker ──
API_HEALTH=$(curl -s --max-time 5 http://localhost:3000/health 2>/dev/null || echo "DOWN")
SCHEDULER_STATUS=$(docker inspect vllm-dashboard-scheduler --format '{{.State.Status}}' 2>/dev/null || echo "DOWN")
COLLECTOR_STATUS=$(docker inspect vllm-dashboard-collector --format '{{.State.Status}}' 2>/dev/null || echo "DOWN")

# ── Backup ──
LAST_BACKUP_TS=$(find "$BACKUP_DIR" -name "*.sql" -printf "%T@\n" 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
LAST_BACKUP_AGE_S=$(( $(date +%s) - ${LAST_BACKUP_TS:-0} ))
LAST_BACKUP_AGE_H=$(( LAST_BACKUP_AGE_S / 3600 ))
[[ -z "$LAST_BACKUP_TS" ]] && LAST_BACKUP_AGE_H=999

# ── 判定 ──
ISSUES=""
[[ "$DISK_USED_PCT" -gt 85 ]] && ISSUES="$ISSUES DISK:$DISK_USED_PCT%"
[[ "$MYSQL_UPTIME" != "running" ]] && ISSUES="$ISSUES MYSQL:DOWN"
[[ "$API_HEALTH" != "healthy" ]] && ISSUES="$ISSUES API:DOWN"
[[ "$SCHEDULER_STATUS" != "running" ]] && ISSUES="$ISSUES SCHEDULER:DOWN"
[[ "$COLLECTOR_STATUS" != "running" ]] && ISSUES="$ISSUES COLLECTOR:DOWN"
[[ "$LAST_BACKUP_AGE_H" -gt 25 ]] && ISSUES="$ISSUES BACKUP:${LAST_BACKUP_AGE_H}h_old"

if $JSON; then
    cat << JSON
{
  "disk_used_pct": $DISK_USED_PCT,
  "mem_avail_mb": $MEM_AVAIL_MB,
  "load": $LOAD,
  "mysql_status": "$MYSQL_UPTIME",
  "mysql_connections": "$MYSQL_CONNS",
  "buffer_pool_hit_pct": "$BUFFER_HIT",
  "slow_queries_1h": "$SLOW_QUERIES_1H",
  "api_health": "$API_HEALTH",
  "scheduler": "$SCHEDULER_STATUS",
  "collector": "$COLLECTOR_STATUS",
  "last_backup_hours_ago": $LAST_BACKUP_AGE_H,
  "issues": "${ISSUES:-none}"
}
JSON
else
    echo "=== vLLM Dashboard Health Check ==="
    echo "Disk:       ${DISK_USED_PCT}% used | Memory: ${MEM_AVAIL_MB}MB avail | Load: $LOAD"
    echo "MySQL:      $MYSQL_UPTIME | Conns: $MYSQL_CONNS | BufferHit: ${BUFFER_HIT}% | SlowQ/1h: $SLOW_QUERIES_1H"
    echo "Services:   API=$API_HEALTH Scheduler=$SCHEDULER_STATUS Collector=$COLLECTOR_STATUS"
    echo "Backup:     ${LAST_BACKUP_AGE_H}h ago"
    [[ -n "$ISSUES" ]] && echo "ISSUES:     $ISSUES" || echo "All clear"
fi
