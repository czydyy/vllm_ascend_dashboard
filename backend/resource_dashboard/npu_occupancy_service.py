"""Normalization and aggregation for the read-through NPU occupancy API."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from resource_dashboard.npu_occupancy_client import NpuOccupancyClient
from resource_dashboard.npu_occupancy_config import (
    POOL_BY_NAME,
    POOLS,
    configured_pool_options,
    is_excluded_cluster,
    resolve_pool,
)

STEP_SECONDS = 120


@dataclass(frozen=True)
class OccupancyRecord:
    env_id: str
    pool: str
    project: str
    workflow: str
    cards: int
    status: str
    created_at: datetime
    effective_end: datetime
    node_ip: str | None
    npu_list: str | None


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace(" ", "T")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if re.search(r"[+-]\d{2}$", text):
        text += ":00"
    elif re.search(r"[+-]\d{4}$", text):
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(re.sub(r"\.(\d+)", "", text))
        except ValueError:
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def npu_cards(env: dict) -> int:
    total = 0
    for device in ((env.get("resource_summary") or {}).get("devices") or []):
        if device.get("res_type") == "npu":
            try:
                total += int(device.get("npu") or 0)
            except (TypeError, ValueError):
                continue
    return total


def project_of(env: dict) -> str:
    comments = env.get("extend_env_comments") or {}
    organization, repository = comments.get("organization"), comments.get("repository")
    if organization and repository:
        return f"{organization}/{repository}"
    if repository:
        return str(repository)
    groups = env.get("groups") or {}
    return sorted(groups)[0] if groups else "未知"


def workflow_of(env: dict) -> str:
    comments = env.get("extend_env_comments") or {}
    return str(comments.get("job_display_name") or env.get("name") or env.get("env_id") or "")


def normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-z]", "", value.lower())


def normalize_records(envs: list[dict], snapshot_at: datetime) -> list[OccupancyRecord]:
    records: list[OccupancyRecord] = []
    seen: set[str] = set()
    for env in envs:
        env_id = str(env.get("env_id") or "")
        if not env_id or env_id in seen or env.get("status") == "rejected":
            continue
        cluster = str(env.get("cluster") or "")
        if is_excluded_cluster(cluster):
            continue
        pool_config = resolve_pool(cluster)
        pool_name = pool_config.name if pool_config else f"未配置:{cluster or '未知资源池'}"
        created_at = parse_timestamp(env.get("created_at"))
        if created_at is None:
            continue
        status = str(env.get("status") or "")
        expires_at = parse_timestamp(env.get("expires_at"))
        effective_end = snapshot_at if status in {"active", "provisioning"} else expires_at
        cards = npu_cards(env)
        if effective_end is None or created_at >= effective_end or cards <= 0:
            continue
        seen.add(env_id)
        npu_list = env.get("npu_list")
        if isinstance(npu_list, list):
            npu_list = ",".join(str(item) for item in npu_list)
        elif npu_list is not None:
            npu_list = str(npu_list)
        records.append(OccupancyRecord(
            env_id=env_id, pool=pool_name, project=project_of(env), workflow=workflow_of(env), cards=cards,
            status=status, created_at=created_at, effective_end=effective_end, node_ip=env.get("node_ip"), npu_list=npu_list,
        ))
    return records


def parse_names(names: str | None) -> list[str]:
    return [name.strip() for name in (names or "").split(",") if name.strip()]


def _bucket_floor(value: datetime) -> datetime:
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - epoch % STEP_SECONDS, tz=UTC)


class NpuOccupancyService:
    def __init__(self, client: NpuOccupancyClient | None = None, envs: list[dict] | None = None, snapshot_at: datetime | None = None):
        self.client = client or NpuOccupancyClient()
        self.envs = envs
        self.snapshot_at = snapshot_at

    def options(self, dimension: str) -> list[dict[str, object]]:
        return configured_pool_options() if dimension == "pool" else []

    def _load(self, start: datetime, end: datetime) -> tuple[list[OccupancyRecord], datetime]:
        if self.envs is not None:
            snapshot_at = self.snapshot_at or datetime.now(UTC)
            return normalize_records(self.envs, snapshot_at), snapshot_at
        snapshot_at = datetime.now(UTC)
        envs = self.client.fetch_window(start, end)
        return normalize_records(envs, snapshot_at), snapshot_at

    @staticmethod
    def _selected(records: list[OccupancyRecord], dimension: str, names: list[str]) -> tuple[list[OccupancyRecord], list[str]]:
        values = [record.pool if dimension == "pool" else record.project for record in records]
        available = [pool.name for pool in POOLS] if dimension == "pool" else sorted(dict.fromkeys(values))
        if not names:
            return records, available
        if dimension == "project":
            canonical = {normalize_key(name) for name in names}
            selected = [record for record in records if normalize_key(record.project) in canonical]
        else:
            selected = [record for record in records if record.pool in names]
        return selected, names

    def trend(self, *, dimension: str, names: list[str], start: datetime, end: datetime) -> dict:
        records, snapshot_at = self._load(start, end)
        records, resolved_names = self._selected(records, dimension, names)
        # A persisted snapshot cannot describe time after it was captured.
        # Stop there rather than rendering those unknown buckets as zero.
        observed_end = min(end, snapshot_at)
        points: list[dict[str, object]] = []
        cursor = _bucket_floor(start)
        while cursor <= observed_end:
            occupied = sum(record.cards for record in records if record.created_at <= cursor < record.effective_end)
            points.append({"timestamp": cursor, "occupied_cards": occupied})
            cursor += timedelta(seconds=STEP_SECONDS)
        values = [point["occupied_cards"] for point in points]
        capacity = None
        # A total that includes unconfigured upstream clusters must never be
        # compared with only the configured pool capacity. Capacity is valid
        # solely for an explicit, fully configured pool selection.
        if dimension == "pool" and names and all(name in POOL_BY_NAME for name in names):
            capacity = sum(POOL_BY_NAME[name].logical_capacity for name in resolved_names if name in POOL_BY_NAME)
        return {
            "dimension": dimension, "names": resolved_names, "start": start, "end": observed_end,
            "sample_interval_seconds": STEP_SECONDS,
            "metrics": {"peak": max(values, default=0), "average": round(sum(values) / len(values), 2) if values else 0, "latest": values[-1] if values else 0, "capacity": capacity},
            "series": points, "snapshot_at": snapshot_at, "data_status": "ready",
        }

    def details(self, *, dimension: str, names: list[str], timestamp: datetime, group_by: str, start: datetime, end: datetime) -> dict:
        records, snapshot_at = self._load(start, end)
        records, resolved_names = self._selected(records, dimension, names)
        groups: dict[str, list[OccupancyRecord]] = defaultdict(list)
        for record in records:
            if record.created_at <= timestamp < record.effective_end:
                groups[record.project if group_by == "project" else record.pool].append(record)
        return {
            "timestamp": timestamp, "dimension": dimension, "names": resolved_names, "group_by": group_by, "snapshot_at": snapshot_at,
            "groups": [
                {"name": name, "occupied_cards": sum(item.cards for item in items), "task_count": len(items), "tasks": [item.__dict__ for item in items]}
                for name, items in sorted(groups.items())
            ],
        }

    def analysis(self, *, dimension: str, names: list[str], start: datetime, end: datetime) -> dict:
        """Aggregate selected groups over the complete requested interval."""
        records, snapshot_at = self._load(start, end)
        records, resolved_names = self._selected(records, dimension, names)
        grouped: dict[str, list[OccupancyRecord]] = defaultdict(list)
        for record in records:
            if record.created_at < end and record.effective_end > start:
                grouped[record.pool if dimension == "pool" else record.project].append(record)

        buckets: list[datetime] = []
        cursor = _bucket_floor(start)
        while cursor <= end:
            buckets.append(cursor)
            cursor += timedelta(seconds=STEP_SECONDS)
        groups = []
        for name, items in grouped.items():
            values = [sum(item.cards for item in items if item.created_at <= point < item.effective_end) for point in buckets]
            groups.append({"name": name, "peak_cards": max(values, default=0), "average_cards": round(sum(values) / len(values), 2) if values else 0, "task_count": len(items), "tasks": [item.__dict__ for item in sorted(items, key=lambda item: (item.created_at, item.workflow))]})
        return {"dimension": dimension, "names": resolved_names, "start": start, "end": end, "sample_interval_seconds": STEP_SECONDS, "groups": sorted(groups, key=lambda group: (-group["peak_cards"], group["name"])), "snapshot_at": snapshot_at}
