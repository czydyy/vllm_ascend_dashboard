"""Integration coverage for Scheduler leadership fencing."""
from __future__ import annotations

import uuid

import pytest

from scheduler.leadership import SchedulerLeaderLease


@pytest.mark.asyncio
async def test_only_one_scheduler_instance_holds_a_lease() -> None:
    from database.migrations.task_queue import run as run_task_queue_migration

    await run_task_queue_migration()
    lease_name = f"test-{uuid.uuid4().hex}"
    first = SchedulerLeaderLease(lease_name=lease_name, ttl_seconds=30)
    second = SchedulerLeaderLease(lease_name=lease_name, ttl_seconds=30)

    assert await first.acquire_or_renew() is True
    assert await second.acquire_or_renew() is False

    await first.release()
    assert await second.acquire_or_renew() is True
    await second.release()
