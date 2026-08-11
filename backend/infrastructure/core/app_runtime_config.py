"""Shared application runtime configuration.

Environment variables bootstrap a service process.  Values changed from the
admin UI are persisted in the MySQL control plane instead of rewriting a
container's ``.env`` file.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.core.config import settings
from infrastructure.db.base import SessionLocal
from infrastructure.persistence.models import ProjectDashboardConfig

APP_RUNTIME_CONFIG_KEY = "app_runtime_config"
APP_RUNTIME_FIELDS = frozenset({"log_level", "debug"})


def _as_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _apply_runtime_config(config: Mapping[str, object]) -> dict[str, object]:
    applied: dict[str, object] = {}
    log_level = config.get("log_level")
    if isinstance(log_level, str) and log_level.upper() in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }:
        settings.LOG_LEVEL = log_level.upper()
        level = getattr(logging, settings.LOG_LEVEL)
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        for handler in root_logger.handlers:
            handler.setLevel(level)
        applied["log_level"] = settings.LOG_LEVEL

    debug = config.get("debug")
    if isinstance(debug, bool):
        settings.DEBUG = debug
        applied["debug"] = debug

    return applied


async def load_app_runtime_config(db: AsyncSession | None = None) -> dict[str, object]:
    """Load application runtime overrides, if present, from MySQL."""
    if db is not None:
        result = await db.execute(
            select(ProjectDashboardConfig).where(
                ProjectDashboardConfig.config_key == APP_RUNTIME_CONFIG_KEY
            )
        )
        row = result.scalar_one_or_none()
        return _apply_runtime_config(_as_mapping(row.config_value) if row else {})

    async with SessionLocal() as session:
        return await load_app_runtime_config(session)


async def persist_app_runtime_config(
    overrides: Mapping[str, object],
    db: AsyncSession | None = None,
) -> None:
    """Persist supported application runtime overrides in the control plane."""
    values = {
        key: value for key, value in overrides.items() if key in APP_RUNTIME_FIELDS
    }
    if not values:
        return

    if db is not None:
        await _persist(db, values)
        return

    async with SessionLocal() as session:
        await _persist(session, values)


async def _persist(db: AsyncSession, values: dict[str, object]) -> None:
    result = await db.execute(
        select(ProjectDashboardConfig).where(
            ProjectDashboardConfig.config_key == APP_RUNTIME_CONFIG_KEY
        )
    )
    row = result.scalar_one_or_none()
    config = _as_mapping(row.config_value) if row else {}
    config.update(values)

    if row is None:
        db.add(
            ProjectDashboardConfig(
                config_key=APP_RUNTIME_CONFIG_KEY,
                config_value=config,
                description="Application runtime configuration owned by the control plane",
            )
        )
    else:
        row.config_value = config

    await db.commit()
