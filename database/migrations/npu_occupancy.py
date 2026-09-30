"""Durable storage for NPU occupancy raw records and sync watermark."""
from __future__ import annotations

import logging

from sqlalchemy import text

from infrastructure.db.base import SessionLocal

logger = logging.getLogger("npu_occupancy_migration")
MIGRATION_VERSION = "20260930_01_npu_occupancy_persistence"


async def run() -> str:
    async with SessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS npu_occupancy_raw_envs (
              id BIGINT NOT NULL AUTO_INCREMENT,
              env_id VARCHAR(255) NOT NULL,
              source_updated_at TIMESTAMP NOT NULL,
              payload JSON NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (id),
              UNIQUE KEY uq_npu_occupancy_env_revision (env_id, source_updated_at),
              KEY ix_npu_occupancy_raw_env_updated (source_updated_at)
            ) ENGINE=InnoDB
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS npu_occupancy_sync_state (
              id INT NOT NULL,
              status VARCHAR(20) NOT NULL DEFAULT 'idle',
              last_successful_sync TIMESTAMP NULL,
              last_snapshot_at TIMESTAMP NULL,
              active_task_id VARCHAR(64) NULL,
              error_message TEXT NULL,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (id)
            ) ENGINE=InnoDB
        """))
        await db.execute(text("""
            INSERT INTO npu_occupancy_sync_state (id, status, updated_at)
            VALUES (1, 'idle', UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE id = VALUES(id)
        """))
        await db.execute(text("""
            INSERT INTO migration_history (version) VALUES (:version)
            ON DUPLICATE KEY UPDATE version = VALUES(version)
        """), {"version": MIGRATION_VERSION})
        await db.commit()
    logger.info("Applied NPU occupancy persistence migration %s", MIGRATION_VERSION)
    return MIGRATION_VERSION
