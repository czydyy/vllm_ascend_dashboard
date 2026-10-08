"""Canonical resource-pool mapping for the NPU occupancy dashboard."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PoolConfig:
    code: str
    name: str
    machine_type: str
    user_capacity: int

    @property
    def logical_capacity(self) -> int:
        return self.user_capacity * 2 if self.machine_type in {"910C", "A3"} else self.user_capacity


POOLS: tuple[PoolConfig, ...] = (
    PoolConfig("hk-001", "参与开源统一资源-香港-910B3", "910B3", 104),
    PoolConfig("gy-004", "SGLang资源池-贵阳-A3", "A3", 112),
    PoolConfig("gy-005", "vllm资源池-贵阳-A3", "A3", 72),
    PoolConfig("aiframework-hb3", "pytorch资源池-华北-910C560T", "910C", 56),
    PoolConfig("verl-hb3", "verl资源池-华北-910C560T", "910C", 72),
    PoolConfig("gy003", "参与开源统一资源-贵阳-310P", "310P", 80),
    PoolConfig("cn12", "参与开源统一资源-华北-910C560T", "910C", 112),
)
EXCLUDED_CODES = frozenset({"gy006"})
POOL_BY_NAME = {pool.name: pool for pool in POOLS}


def resolve_pool(cluster: str | None) -> PoolConfig | None:
    """Match an upstream cluster code exactly or by its configured instance prefix."""
    value = (cluster or "").strip()
    if not value:
        return None
    if value in EXCLUDED_CODES or any(value.startswith(f"{code}-") for code in EXCLUDED_CODES):
        return None
    for pool in POOLS:
        if value == pool.code or value.startswith(f"{pool.code}-"):
            return pool
    return None


def is_excluded_cluster(cluster: str | None) -> bool:
    value = (cluster or "").strip()
    return value in EXCLUDED_CODES or any(value.startswith(f"{code}-") for code in EXCLUDED_CODES)


def configured_pool_options() -> list[dict[str, object]]:
    return [
        {"name": pool.name, "label": pool.name, "capacity": pool.logical_capacity, "configured": True}
        for pool in POOLS
    ]
