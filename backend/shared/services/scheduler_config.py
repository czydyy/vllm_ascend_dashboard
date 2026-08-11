"""Durable configuration channel from the API control plane to Scheduler."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select, text

from shared.db.base import SessionLocal
from shared.models import ProjectDashboardConfig

SCHEDULER_RUNTIME_CONFIG_KEY = "scheduler_runtime_config"

# Only scheduling inputs belong in this cross-process configuration document.
SCHEDULER_RUNTIME_FIELDS = frozenset(
    {
        "ci_sync_interval_minutes",
        "ci_sync_days_back",
        "ci_sync_max_runs_per_workflow",
        "ci_sync_force_full_refresh",
        "model_sync_interval_minutes",
        "model_sync_days_back",
        "model_sync_runs_limit",
        "project_dashboard_cache_interval_minutes",
        "data_retention_days",
    }
)


async def persist_scheduler_runtime_config(overrides: dict[str, Any]) -> None:
    """Persist scheduler inputs and emit a durable reload command.

    The API never mutates another process's APScheduler object.  The Scheduler
    consumes this command from MySQL and reloads its own local schedule.
    """
    values = {key: value for key, value in overrides.items() if key in SCHEDULER_RUNTIME_FIELDS}
    if not values:
        return

    async with SessionLocal() as db:
        async with db.begin():
            result = await db.execute(
                select(ProjectDashboardConfig).where(
                    ProjectDashboardConfig.config_key == SCHEDULER_RUNTIME_CONFIG_KEY
                )
            )
            row = result.scalar_one_or_none()
            config = dict(row.config_value or {}) if row else {}
            config.update(values)
            if row is None:
                db.add(
                    ProjectDashboardConfig(
                        config_key=SCHEDULER_RUNTIME_CONFIG_KEY,
                        config_value=config,
                        description="Scheduler runtime configuration owned by the control plane",
                    )
                )
            else:
                row.config_value = config

            await db.execute(
                text(
                    """
                    INSERT INTO control_outbox
                        (event_id, aggregate_type, aggregate_id, event_type, aggregate_version, payload)
                    VALUES
                        (:event_id, 'scheduler', 'runtime-config', 'scheduler.config.reload', :version, :payload)
                    """
                ),
                {
                    "event_id": str(uuid.uuid4()),
                    "version": 1,
                    "payload": json.dumps({"changed": sorted(values)}),
                },
            )
