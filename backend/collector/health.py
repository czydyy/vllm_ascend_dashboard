"""Container health probe backed by the Collector's durable heartbeat."""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import text


def _node_id() -> str:
    return os.environ.get("NODE_ID", f"collector-{os.uname().nodename}")


async def is_healthy() -> bool:
    from infrastructure.db.base import SessionLocal

    async with SessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "SELECT running, updated_at FROM collector_heartbeats "
                    "WHERE node_id = :node_id"
                ),
                {"node_id": _node_id()},
            )
        ).one_or_none()
    if row is None or not row.running or row.updated_at is None:
        return False
    updated_at = row.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - updated_at < timedelta(seconds=60)


def main() -> None:
    raise SystemExit(0 if asyncio.run(is_healthy()) else 1)


if __name__ == "__main__":
    main()
