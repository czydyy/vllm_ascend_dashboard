"""Scheduler dispatch must create durable work instead of doing GitHub I/O."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from scheduler.service import DataSyncScheduler
from shared.db.base import SessionLocal, engine


@pytest.mark.asyncio
async def test_pr_schedule_enqueues_a_collector_task() -> None:
    from database.migrations.task_queue import run as run_task_queue_migration

    await run_task_queue_migration()
    scheduler = DataSyncScheduler()
    try:
        await scheduler._sync_pr_pipeline_job()
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT task_type, task_params, status, required_capability "
                        "FROM collection_tasks "
                        "WHERE dedupe_key LIKE 'pr_sync:scheduled:%' "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
            ).one()

        assert row.task_type == "pr_sync"
        assert row.status == "pending"
        assert row.required_capability == "python"
        assert "days_back" in row.task_params
    finally:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)
        await engine.dispose()
