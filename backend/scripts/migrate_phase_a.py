"""Phase A schema migration: collection_tasks, control_outbox, scheduler_leader_lease.

Idempotent — safe to run repeatedly. Never creates, resets, or deletes users.
Run only after a verified database backup has been created (Step 0.1).
"""
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.base import SessionLocal, engine

logger = logging.getLogger("phase_a_migration")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

MIGRATION_VERSION = "20260805_01_phase_a_tables"

# ── collection_tasks: 采集任务与租约 ──
COLLECTION_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS collection_tasks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL,
    task_params JSON NOT NULL,
    status ENUM('pending','running','completed','failed','dead') NOT NULL DEFAULT 'pending',

    -- 租约（fencing token 防重启覆盖）
    lease_owner VARCHAR(100),
    lease_token VARCHAR(64),
    lease_generation BIGINT NOT NULL DEFAULT 0,
    lease_expiry DATETIME,

    -- 能力过滤
    required_capability VARCHAR(50),

    -- 优先级与重试
    priority INT NOT NULL DEFAULT 0,
    execution_count INT NOT NULL DEFAULT 0,
    failure_count   INT NOT NULL DEFAULT 0,
    max_failures    INT DEFAULT 3,
    next_retry_at DATETIME,

    -- 检查点
    checkpoint_data JSON,

    -- 幂等去重
    dedupe_key VARCHAR(255) NOT NULL,
    active_dedupe_key VARCHAR(255)
      GENERATED ALWAYS AS (
        CASE WHEN status IN ('pending', 'running') THEN dedupe_key ELSE NULL END
      ) STORED,

    -- 错误信息
    last_error TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_status_expiry (status, lease_expiry),
    INDEX idx_lease_owner (lease_owner),
    UNIQUE INDEX uk_active_dedupe (active_dedupe_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ── control_outbox: 配置变更可靠投递 ──
CONTROL_OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS control_outbox (
    event_id CHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_by VARCHAR(100),
    claim_token CHAR(36),
    claim_expiry DATETIME,
    processed_at DATETIME,
    last_error TEXT,
    UNIQUE KEY uk_aggregate_event (
        aggregate_type, aggregate_id, aggregate_version, event_type
    ),
    INDEX idx_outbox_pending (processed_at, claim_expiry, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ── scheduler_leader_lease: Scheduler 高可用 ──
SCHEDULER_LEADER_LEASE_DDL = """
CREATE TABLE IF NOT EXISTS scheduler_leader_lease (
    lease_name VARCHAR(50) PRIMARY KEY,
    lease_owner VARCHAR(100) NOT NULL,
    lease_token CHAR(36) NOT NULL,
    lease_expiry DATETIME NOT NULL,
    generation BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ── migration_history: 防重复执行 ──
MIGRATION_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS migration_history (
    version VARCHAR(100) PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR(64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ── 兼容性 ALTER：如果已有简化版 collection_tasks 旧表 ──
COLLECTION_TASKS_ALTER = """
ALTER TABLE collection_tasks
  ADD COLUMN IF NOT EXISTS lease_token VARCHAR(64),
  ADD COLUMN IF NOT EXISTS lease_generation BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS required_capability VARCHAR(50),
  ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS execution_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS failure_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_failures INT NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS next_retry_at DATETIME,
  ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(255),
  ADD COLUMN IF NOT EXISTS active_dedupe_key VARCHAR(255)
    GENERATED ALWAYS AS (
      CASE WHEN status IN ('pending', 'running') THEN dedupe_key ELSE NULL END
    ) STORED,
  MODIFY COLUMN status ENUM('pending','running','completed','failed','dead') NOT NULL DEFAULT 'pending',
  ADD UNIQUE INDEX IF NOT EXISTS uk_active_dedupe (active_dedupe_key);
"""


async def _table_exists(name: str) -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :name LIMIT 1"),
            {"name": name},
        )
        return result.fetchone() is not None


async def _column_exists(table: str, column: str) -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :column LIMIT 1"
            ),
            {"table": table, "column": column},
        )
        return result.fetchone() is not None


async def _is_migration_applied(version: str) -> bool:
    if not await _table_exists("migration_history"):
        return False
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM migration_history WHERE version = :version LIMIT 1"),
            {"version": version},
        )
        return result.fetchone() is not None


async def run():
    if await _is_migration_applied(MIGRATION_VERSION):
        logger.info("Migration %s already applied, skipping.", MIGRATION_VERSION)
        return

    async with engine.begin() as conn:
        # migration_history 总要最先建
        logger.info("Creating migration_history...")
        await conn.execute(text(MIGRATION_HISTORY_DDL))

        # collection_tasks
        if await _table_exists("collection_tasks"):
            logger.info("collection_tasks exists, applying ALTER...")
            try:
                await conn.execute(text(COLLECTION_TASKS_ALTER))
                logger.info("collection_tasks ALTER applied.")
            except Exception as exc:
                logger.warning("collection_tasks ALTER failed (may already be current): %s", exc)
        else:
            logger.info("Creating collection_tasks...")
            await conn.execute(text(COLLECTION_TASKS_DDL))

        # control_outbox
        if not await _table_exists("control_outbox"):
            logger.info("Creating control_outbox...")
            await conn.execute(text(CONTROL_OUTBOX_DDL))
        else:
            logger.info("control_outbox already exists, skipping.")

        # scheduler_leader_lease
        if not await _table_exists("scheduler_leader_lease"):
            logger.info("Creating scheduler_leader_lease...")
            await conn.execute(text(SCHEDULER_LEADER_LEASE_DDL))
        else:
            logger.info("scheduler_leader_lease already exists, skipping.")

        # 记录迁移
        await conn.execute(
            text("INSERT INTO migration_history (version) VALUES (:version)"),
            {"version": MIGRATION_VERSION},
        )

    logger.info("Phase A migration %s complete.", MIGRATION_VERSION)


if __name__ == "__main__":
    asyncio.run(run())
