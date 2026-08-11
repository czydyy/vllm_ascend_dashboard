"""MySQL-only test database helpers."""

from __future__ import annotations

import os
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.schema import Table, sort_tables

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://dashboard:dashboard123@127.0.0.1:3308/vllm_dashboard_test",
)


def create_test_engine() -> AsyncEngine:
    """Return the dedicated MySQL integration-test engine."""
    return create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)


async def reset_tables(engine: AsyncEngine, tables: Iterable[Table]) -> None:
    """Drop and recreate only the tables owned by one test fixture."""
    table_list = list(sort_tables(list(tables)))

    def recreate(sync_conn) -> None:
        # Fixtures reset a subset of a shared integration database. Other
        # tables can hold foreign keys into that subset, so MySQL must not
        # enforce those constraints while the owned tables are recreated.
        sync_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for table in reversed(table_list):
                table.drop(sync_conn, checkfirst=True)
            for table in table_list:
                table.create(sync_conn, checkfirst=True)
        finally:
            sync_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    async with engine.begin() as conn:
        await conn.run_sync(recreate)
        await conn.execute(text("SET SESSION sql_mode = 'STRICT_TRANS_TABLES'"))
