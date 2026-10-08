from datetime import UTC, datetime

from resource_dashboard.npu_occupancy_service import (
    NpuOccupancyService,
    normalize_records,
    npu_cards,
    parse_timestamp,
)


def _env(*, env_id: str, cluster: str, status: str, created: str, expires: str | None, cards: int, project: str = "org/repo") -> dict:
    organization, repository = project.split("/", 1)
    return {
        "env_id": env_id, "cluster": cluster, "status": status, "created_at": created, "expires_at": expires,
        "extend_env_comments": {"organization": organization, "repository": repository, "job_display_name": env_id},
        "resource_summary": {"devices": [{"res_type": "npu", "npu": cards}, {"res_type": "container", "npu": 99}]},
        "node_ip": "10.0.0.1", "npu_list": "0,1",
    }


class _Client:
    def __init__(self, envs: list[dict]):
        self.envs = envs

    def fetch_window(self, start, end):
        return self.envs


def test_normalization_matches_pipeline_card_and_interval_rules():
    snapshot = datetime(2026, 9, 1, 10, 10, tzinfo=UTC)
    envs = [
        _env(env_id="active", cluster="gy-004", status="active", created="2026-09-01T10:00:00Z", expires=None, cards=8),
        _env(env_id="expired", cluster="gy-005", status="expired", created="2026-09-01T10:00:00Z", expires="2026-09-01T10:04:00Z", cards=4),
        _env(env_id="rejected", cluster="gy-004", status="rejected", created="2026-09-01T10:00:00Z", expires=None, cards=32),
        _env(env_id="excluded", cluster="gy006", status="active", created="2026-09-01T10:00:00Z", expires=None, cards=16),
    ]
    records = normalize_records(envs, snapshot)
    assert [record.env_id for record in records] == ["active", "expired"]
    assert npu_cards(envs[0]) == 8
    assert parse_timestamp("2026-09-01 10:00:00.86+00") == datetime(2026, 9, 1, 10, 0, 0, 860000, tzinfo=UTC)

    service = NpuOccupancyService(client=_Client(envs))
    result = service.trend(dimension="pool", names=[], start=datetime(2026, 9, 1, 10, 0, tzinfo=UTC), end=datetime(2026, 9, 1, 10, 6, tzinfo=UTC))
    assert [point["occupied_cards"] for point in result["series"]] == [12, 12, 8, 8]
    assert result["metrics"]["peak"] == 12
    assert result["metrics"]["latest"] == 8
    assert result["metrics"]["capacity"] is None


def test_project_aliases_and_pool_selection_do_not_double_count():
    envs = [
        _env(env_id="one", cluster="gy-004", status="active", created="2026-09-01T10:00:00Z", expires=None, cards=8, project="org/repo"),
        _env(env_id="two", cluster="gy-005", status="active", created="2026-09-01T10:00:00Z", expires=None, cards=4, project="org/repo"),
    ]
    service = NpuOccupancyService(client=_Client(envs))
    start, end = datetime(2026, 9, 1, 10, 0, tzinfo=UTC), datetime(2026, 9, 1, 10, 2, tzinfo=UTC)
    project = service.trend(dimension="project", names=["org-repo"], start=start, end=end)
    pools = service.trend(dimension="pool", names=["SGLang资源池-贵阳-A3", "vllm资源池-贵阳-A3"], start=start, end=end)
    assert project["series"][0]["occupied_cards"] == 12
    assert pools["series"][0]["occupied_cards"] == 12
    assert project["metrics"]["capacity"] is None


def test_range_analysis_uses_the_whole_interval_not_one_snapshot():
    envs = [
        _env(env_id="long", cluster="gy-004", status="active", created="2026-09-01T10:00:00Z", expires=None, cards=8),
        _env(env_id="short", cluster="gy-004", status="expired", created="2026-09-01T10:00:00Z", expires="2026-09-01T10:04:00Z", cards=4),
    ]
    service = NpuOccupancyService(client=_Client(envs))
    start = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    end = datetime(2026, 9, 1, 10, 6, tzinfo=UTC)

    result = service.analysis(dimension="project", names=[], start=start, end=end)

    assert len(result["groups"]) == 1
    group = result["groups"][0]
    assert group["task_count"] == 2
    assert group["peak_cards"] == 12
    assert group["average_cards"] == 10
