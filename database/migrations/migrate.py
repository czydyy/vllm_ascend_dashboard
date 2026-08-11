"""Canonical database migration command for the dashboard.

This command is safe to repeat: it creates missing current-schema tables and
then applies the explicit MySQL compatibility and task-queue migrations. It
never creates, resets, or deletes application users.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text

repository_root = Path(__file__).resolve().parents[2]
# Source checkouts keep application code under ``backend/``; the production
# image copies it directly to ``/app``.  Support both layouts without making
# the migration command depend on its former ``backend/scripts`` location.
application_root = repository_root / "backend"
if not application_root.is_dir():
    application_root = repository_root
sys.path.insert(0, str(application_root))

from app.db.base import SessionLocal, engine
if (repository_root / "backend").is_dir():
    from database.bootstrap import create_tables_with_latest_schema
    from database.migrations.mysql_schema import migrate as migrate_mysql_schema
    from database.migrations.task_queue import run as migrate_phase_a
else:
    from scripts.init_db import create_tables_with_latest_schema
    from scripts.migration.mysql_schema import migrate as migrate_mysql_schema
    from scripts.migration.task_queue import run as migrate_phase_a

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("database_migration")


async def _user_count() -> int:
    async with SessionLocal() as db:
        return int((await db.execute(text("SELECT COUNT(*) FROM users"))).scalar_one())


async def migrate() -> None:
    if engine.dialect.name != "mysql":
        raise RuntimeError(f"Production migration requires MySQL, got {engine.dialect.name}")

    users_before = await _user_count()
    await create_tables_with_latest_schema()
    await migrate_mysql_schema()
    await migrate_phase_a()
    users_after = await _user_count()
    if users_after != users_before:
        raise RuntimeError(
            f"User count changed during migration: {users_before} -> {users_after}"
        )
    logger.info("Migration completed; users=%d", users_after)


async def main() -> None:
    try:
        await migrate()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
