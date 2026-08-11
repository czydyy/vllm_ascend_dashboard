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


@pytest.mark.asyncio
async def test_ci_schedule_enqueues_a_collector_task() -> None:
    from database.migrations.task_queue import run as run_task_queue_migration

    await run_task_queue_migration()
    scheduler = DataSyncScheduler()
    try:
        await scheduler._sync_ci_data_job()
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT task_type, task_params, status, required_capability "
                        "FROM collection_tasks "
                        "WHERE dedupe_key LIKE 'ci_sync:scheduled:%' "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
            ).one()

        assert row.task_type == "ci_sync"
        assert row.status == "pending"
        assert row.required_capability == "python"
        assert "days_back" in row.task_params
        assert "max_runs" in row.task_params
    finally:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)
        await engine.dispose()


@pytest.mark.asyncio
async def test_model_schedule_enqueues_a_collector_task() -> None:
    from database.migrations.task_queue import run as run_task_queue_migration

    await run_task_queue_migration()
    scheduler = DataSyncScheduler()
    try:
        await scheduler._sync_model_reports_job()
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT task_type, task_params, status, required_capability "
                        "FROM collection_tasks "
                        "WHERE dedupe_key LIKE 'model_sync:scheduled:%' "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
            ).one()

        assert row.task_type == "model_sync"
        assert row.status == "pending"
        assert row.required_capability == "python"
        assert "days_back" in row.task_params
        assert "runs_limit" in row.task_params
    finally:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)
        await engine.dispose()


@pytest.mark.asyncio
async def test_code_metrics_schedule_enqueues_a_collector_task() -> None:
    from database.migrations.task_queue import run as run_task_queue_migration

    await run_task_queue_migration()
    scheduler = DataSyncScheduler()
    try:
        await scheduler._collect_code_metrics_job()
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT task_type, task_params, status, required_capability "
                        "FROM collection_tasks "
                        "WHERE dedupe_key LIKE 'code_metrics:scheduled:%' "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
            ).one()

        assert row.task_type == "code_metrics_collect"
        assert row.status == "pending"
        assert row.required_capability == "python"
        assert "main" in row.task_params
    finally:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)
        await engine.dispose()


@pytest.mark.asyncio
async def test_heatmap_schedule_enqueues_a_collector_task() -> None:
    from database.migrations.task_queue import run as run_task_queue_migration

    await run_task_queue_migration()
    scheduler = DataSyncScheduler()
    try:
        await scheduler._sync_heatmap_job()
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT task_type, task_params, status, required_capability "
                        "FROM collection_tasks "
                        "WHERE dedupe_key LIKE 'code_heatmap_sync:scheduled:%' "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
            ).one()

        assert row.task_type == "code_heatmap_sync"
        assert row.status == "pending"
        assert row.required_capability == "python"
        assert "days" in row.task_params
    finally:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)
        await engine.dispose()
