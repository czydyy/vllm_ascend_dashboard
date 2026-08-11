"""Container health probe backed by the Scheduler's durable heartbeat."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta


async def is_healthy() -> bool:
    from shared.db.base import SessionLocal
    from shared.models import SchedulerHeartbeat

    async with SessionLocal() as db:
        heartbeat = await db.get(SchedulerHeartbeat, 1)
    if heartbeat is None or not heartbeat.running or heartbeat.updated_at is None:
        return False
    updated_at = heartbeat.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - updated_at < timedelta(seconds=90)


def main() -> None:
    raise SystemExit(0 if asyncio.run(is_healthy()) else 1)


if __name__ == "__main__":
    main()
