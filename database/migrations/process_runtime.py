"""Runtime-status tables for independent Scheduler and Collector processes."""
from __future__ import annotations

import logging

from sqlalchemy import text

from infrastructure.db.base import engine

logger = logging.getLogger(__name__)

MIGRATION_VERSION = "20260811_01_process_runtime_status"

COLLECTOR_HEARTBEATS_DDL = """
CREATE TABLE IF NOT EXISTS collector_heartbeats (
    node_id VARCHAR(100) PRIMARY KEY,
    capabilities JSON NOT NULL,
    running BOOLEAN NOT NULL DEFAULT FALSE,
    active_tasks INT NOT NULL DEFAULT 0,
    pid INT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_collector_heartbeats_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


async def run() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS migration_history (
                    version VARCHAR(100) PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    checksum VARCHAR(64)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        existing = await conn.execute(
            text("SELECT 1 FROM migration_history WHERE version = :version"),
            {"version": MIGRATION_VERSION},
        )
        if existing.fetchone():
            return
        await conn.execute(text(COLLECTOR_HEARTBEATS_DDL))
        await conn.execute(
            text("INSERT INTO migration_history (version) VALUES (:version)"),
            {"version": MIGRATION_VERSION},
        )
    logger.info("Applied process runtime migration %s", MIGRATION_VERSION)
