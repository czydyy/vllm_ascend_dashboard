from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

NpuOccupancyDimension = Literal["pool", "project"]
NpuOccupancyGroupBy = Literal["pool", "project"]


class NpuOccupancyMetrics(BaseModel):
    peak: int = 0
    average: float = 0
    latest: int = 0
    capacity: int | None = None


class NpuOccupancySeriesPoint(BaseModel):
    timestamp: datetime
    occupied_cards: int


class NpuOccupancyTrendResponse(BaseModel):
    dimension: NpuOccupancyDimension
    names: list[str] = Field(default_factory=list)
    start: datetime
    end: datetime
    sample_interval_seconds: int = 120
    metrics: NpuOccupancyMetrics
    series: list[NpuOccupancySeriesPoint] = Field(default_factory=list)
    snapshot_at: datetime
    data_status: Literal["ready"] = "ready"


class NpuOccupancyOption(BaseModel):
    name: str
    label: str
    capacity: int | None = None
    configured: bool = True


class NpuOccupancyOptionsResponse(BaseModel):
    dimension: NpuOccupancyDimension
    options: list[NpuOccupancyOption] = Field(default_factory=list)


class NpuOccupancyTask(BaseModel):
    env_id: str
    project: str
    pool: str
    workflow: str
    cards: int
    node_ip: str | None = None
    npu_list: str | None = None
    status: str
    created_at: datetime
    effective_end: datetime


class NpuOccupancyDetailGroup(BaseModel):
    name: str
    occupied_cards: int
    task_count: int
    tasks: list[NpuOccupancyTask] = Field(default_factory=list)


class NpuOccupancyDetailsResponse(BaseModel):
    timestamp: datetime
    dimension: NpuOccupancyDimension
    names: list[str] = Field(default_factory=list)
    group_by: NpuOccupancyGroupBy
    groups: list[NpuOccupancyDetailGroup] = Field(default_factory=list)
    snapshot_at: datetime


class NpuOccupancyAnalysisGroup(BaseModel):
    name: str
    peak_cards: int
    average_cards: float
    task_count: int
    tasks: list[NpuOccupancyTask] = Field(default_factory=list)


class NpuOccupancyAnalysisResponse(BaseModel):
    dimension: NpuOccupancyDimension
    names: list[str] = Field(default_factory=list)
    start: datetime
    end: datetime
    sample_interval_seconds: int = 120
    groups: list[NpuOccupancyAnalysisGroup] = Field(default_factory=list)
    snapshot_at: datetime
