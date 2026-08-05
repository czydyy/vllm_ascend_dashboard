#!/bin/bash
# MySQL 副本提升为 Primary —— 计划切换（Switchover）用。
# 紧急 Failover 时 Primary 不可达，不应复用此脚本；参考架构文档"流程二"。
# 状态：设计示例，未完成生产演练前禁止直接执行。
set -euo pipefail

FORCE_ACCEPT_DATA_LOSS=false
if [[ "${1:-}" == "--force-accept-data-loss" ]]; then
    FORCE_ACCEPT_DATA_LOSS=true
    shift
fi
NEW_PRIMARY="${1:-}"
if [[ -z "$NEW_PRIMARY" ]]; then
    echo "Usage: $0 [--force-accept-data-loss] <new-primary-hostname>"
    exit 2
fi

echo "=== Step 0: Fence 旧 Primary（在外部执行） ==="
echo "请确认旧 Primary 已通过以下方式之一隔离："
echo "  - 整机关机（云控制台 / 物理断电）"
echo "  - 整机网络隔离"
echo "  - 停止旧 Primary 上的 MySQL + Control + Scheduler 容器"
echo ""
echo "仅阻断 3306 端口或 Tailscale ACL 撤销不足以保证 fencing。"
read -r -p "旧 Primary 已隔离？(yes/no): " confirmed
[[ "$confirmed" != "yes" ]] && exit 1

echo "=== Step 1: 选择数据最完整的副本 ==="
GTID_A=$(mysql -h node-a -N -e "SELECT @@GLOBAL.gtid_executed" 2>/dev/null || echo "")
GTID_B=$(mysql -h node-b -N -e "SELECT @@GLOBAL.gtid_executed" 2>/dev/null || echo "")

if [[ -n "$GTID_A" && -n "$GTID_B" ]]; then
    A_CONTAINS_B=$(mysql -h node-a -N -e "SELECT GTID_SUBSET('$GTID_B', '$GTID_A')")
    B_CONTAINS_A=$(mysql -h node-b -N -e "SELECT GTID_SUBSET('$GTID_A', '$GTID_B')")

    if [[ "$NEW_PRIMARY" == "node-a" && "$A_CONTAINS_B" != "1" ]]; then
        echo "ERROR: Node A 的 GTID 不是 Node B 的超集！停止切换"
        exit 1
    elif [[ "$NEW_PRIMARY" == "node-b" && "$B_CONTAINS_A" != "1" ]]; then
        echo "ERROR: Node B 的 GTID 不是 Node A 的超集！停止切换"
        exit 1
    elif [[ "$A_CONTAINS_B" != "1" && "$B_CONTAINS_A" != "1" ]]; then
        echo "ERROR: 两个副本的 GTID 互不为超集，可能存在脑裂！禁止自动提升"
        exit 1
    fi
fi

echo "=== Step 1b: 仅一个副本可达时的安全检查 ==="
if [[ -z "$GTID_A" || -z "$GTID_B" ]]; then
    echo "WARN: 无法同时读取两个副本的 GTID。可能另一个副本不可达或尚未配置。"
    if [[ "$FORCE_ACCEPT_DATA_LOSS" != "true" ]]; then
        echo "ERROR: 仅一个副本可达时默认拒绝切换。使用 --force-accept-data-loss 显式接受风险。"
        exit 1
    fi
    echo "WARN: --force-accept-data-loss 已设置，继续切换。"
fi

echo "=== Step 2: 强制校验复制健康状态 ==="
REPLICA_STATUS=$(mysql -h "$NEW_PRIMARY" -N -e "SHOW REPLICA STATUS\G" 2>/dev/null)
IO_RUNNING=$(echo "$REPLICA_STATUS" | grep Replica_IO_Running | awk '{print $2}')
SQL_RUNNING=$(echo "$REPLICA_STATUS" | grep Replica_SQL_Running | awk '{print $2}')
IO_ERROR=$(echo "$REPLICA_STATUS" | grep Last_IO_Error | awk -F': ' '{print $2}' | xargs)
SQL_ERROR=$(echo "$REPLICA_STATUS" | grep Last_SQL_Error | awk -F': ' '{print $2}' | xargs)
SECONDS_BEHIND=$(echo "$REPLICA_STATUS" | grep Seconds_Behind_Source | awk '{print $2}')
RETRIEVED_GTID=$(echo "$REPLICA_STATUS" | grep Retrieved_Gtid_Set | awk -F': ' '{print $2}' | xargs)
EXECUTED_GTID=$(echo "$REPLICA_STATUS" | grep Executed_Gtid_Set | awk -F': ' '{print $2}' | xargs)

[[ "$IO_RUNNING" != "Yes" ]] && echo "ERROR: Replica_IO_Running=$IO_RUNNING（计划切换要求 I/O 线程健康；紧急场景请使用 Failover 流程）" && exit 1
[[ "$SQL_RUNNING" != "Yes" ]] && echo "ERROR: Replica_SQL_Running=$SQL_RUNNING" && exit 1
[[ -n "$IO_ERROR" ]] && echo "ERROR: Last_IO_Error=$IO_ERROR" && exit 1
[[ -n "$SQL_ERROR" ]] && echo "ERROR: Last_SQL_Error=$SQL_ERROR" && exit 1

if [[ "$RETRIEVED_GTID" != "$EXECUTED_GTID" ]]; then
    echo "WARN: Retrieved GTID 未完全执行。使用 GTID_SUBSET 判断..."
    IS_SUBSET=$(mysql -h "$NEW_PRIMARY" -N -e "SELECT GTID_SUBSET('$RETRIEVED_GTID', '$EXECUTED_GTID')")
    if [[ "$IS_SUBSET" != "1" ]]; then
        echo "ERROR: Retrieved GTID 不是 Executed GTID 的子集"
        exit 1
    fi
fi

if [[ "$SECONDS_BEHIND" != "0" ]]; then
    if [[ "$FORCE_ACCEPT_DATA_LOSS" != "true" ]]; then
        echo "ERROR: 副本落后 ${SECONDS_BEHIND}s。如需强制提升，传 --force-accept-data-loss"
        exit 1
    fi
    echo "WARN: --force-accept-data-loss 已设置，将以数据损失为代价提升"
fi

echo "=== Step 3: 提升为 Primary ==="
mysql -h "$NEW_PRIMARY" -e "
  STOP REPLICA;
  RESET REPLICA ALL;
  SET GLOBAL read_only = OFF;
  SET GLOBAL super_read_only = OFF;
  SET PERSIST read_only = OFF;
  SET PERSIST super_read_only = OFF;
"
echo "新 Primary: $NEW_PRIMARY"

echo "=== Step 4: 更新数据库连接入口 ==="
echo "请更新内部 DNS：db.internal 指向 $NEW_PRIMARY 的 Tailscale IP"
echo "等待 DNS TTL（~30s）过期后，重启应用容器或等待连接池重建。"
read -r -p "DNS 已更新且所有应用节点解析正确？(yes/no): " confirmed
[[ "$confirmed" != "yes" ]] && echo "WARN: DNS 未确认，后续步骤可能失败"

echo "=== Step 5: 将另一个副本指向新主 ==="
if [[ "$NEW_PRIMARY" == "node-a" ]]; then
    OTHER_REPLICA="node-b"
elif [[ "$NEW_PRIMARY" == "node-b" ]]; then
    OTHER_REPLICA="node-a"
else
    echo "未知的 NEW_PRIMARY: $NEW_PRIMARY"
    read -r -p "另一个副本的 hostname: " OTHER_REPLICA
fi

mysql -h "$OTHER_REPLICA" -e "
  STOP REPLICA;
  CHANGE REPLICATION SOURCE TO
    SOURCE_HOST='$NEW_PRIMARY',
    SOURCE_AUTO_POSITION = 1;
  START REPLICA;
" 2>/dev/null || echo "WARN: 无法将 $OTHER_REPLICA 指向新主（可能尚未配置或不可达）"
echo "另一个副本 $OTHER_REPLICA 操作完成"

echo "=== Step 6: 验证新主可写 ==="
mysql -h "$NEW_PRIMARY" -e "
  SELECT @@hostname, @@server_id, @@read_only, @@super_read_only;
  SHOW MASTER STATUS;
"
mysql -h "$NEW_PRIMARY" -e "
  CREATE TABLE IF NOT EXISTS control_db.ha_canary (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    checked_at DATETIME NOT NULL
  );
  START TRANSACTION;
  INSERT INTO control_db.ha_canary(checked_at) VALUES (NOW());
  ROLLBACK;
"
echo "新主写入验证通过"

echo "=== Step 7: 验证另一个副本跟上新主 ==="
sleep 3
mysql -h "$OTHER_REPLICA" -e "SHOW REPLICA STATUS\G" 2>/dev/null | grep -E "Replica_IO_Running|Replica_SQL_Running|Seconds_Behind_Source" || echo "WARN: 无法读取 $OTHER_REPLICA 状态"

echo ""
echo "=== 切换完成 ==="
echo "新 Primary: $NEW_PRIMARY"
echo ""
echo "=== 旧主恢复后的处理 ==="
echo "旧主可能持有尚未复制到新主的额外事务（errant GTID）。"
echo "1. 旧主启动后立即设为只读"
echo "2. 比较旧主与新主的 @@GLOBAL.gtid_executed"
echo "3. 如果旧主 GTID 是新主子集 → 从新主全量克隆后作为 Replica 加入"
echo "4. 如果旧主有额外 GTID → 导出审查后全量克隆加入"
echo "5. 禁止不经 GTID 比较直接 CHANGE REPLICATION SOURCE"
