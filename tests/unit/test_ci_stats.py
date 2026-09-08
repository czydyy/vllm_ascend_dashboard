from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import mysql

from api.v1.ci import get_ci_stats, list_runs
from contracts.schemas import CIStats


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _OneResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _ScalarsResult:
    def scalars(self):
        return self

    def all(self):
        return []


@pytest.mark.asyncio
async def test_ci_runs_filter_and_order_by_workflow_start_time():
    db = AsyncMock()
    db.execute.side_effect = [
        _RowsResult([("nightly", None, None)]),
        _ScalarsResult(),
    ]

    await list_runs(
        db,
        start_time=datetime(2026, 9, 1, tzinfo=UTC),
        end_time=datetime(2026, 9, 7, tzinfo=UTC),
        limit=100,
    )

    statement = db.execute.await_args_list[1].args[0]
    sql = str(statement.compile(
        dialect=mysql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))
    assert "ci_results.started_at >=" in sql
    assert "ci_results.started_at <=" in sql
    assert "ORDER BY ci_results.started_at DESC" in sql
    assert "coalesce(ci_results.completed_at, ci_results.started_at)" not in sql


@pytest.mark.asyncio
async def test_ci_stats_combines_workflow_and_hardware_filters_for_all_aggregates():
    db = AsyncMock()
    db.execute.side_effect = [
        _RowsResult([("nightly", None, None)]),
        _OneResult(SimpleNamespace(
            total_runs=4,
            passed_runs=1,
            failed_runs=1,
            avg_duration=90,
        )),
        _OneResult(SimpleNamespace(runs=2, success_runs=1, avg_duration=60)),
    ]

    result = await get_ci_stats(
        db,
        workflow_name="nightly",
        hardware="A2",
        start_time=datetime(2026, 9, 1, tzinfo=UTC),
        end_time=datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert result["total_runs"] == 4
    assert result["passed_runs"] == 1
    assert result["failed_runs"] == 1
    assert result["other_runs"] == 2
    assert result["success_rate"] == 25.0
    assert result["last_7_days"]["success_rate"] == 50.0

    aggregate_statements = [call.args[0] for call in db.execute.await_args_list[1:]]
    for statement in aggregate_statements:
        sql = str(statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))
        assert "ci_results.workflow_name = 'nightly'" in sql
        assert "ci_results.hardware = 'A2'" in sql
        assert "ci_results.started_at >=" in sql
        assert "ci_results.started_at <=" in sql
        assert "coalesce(ci_results.completed_at, ci_results.started_at)" not in sql


@pytest.mark.asyncio
async def test_ci_stats_returns_all_count_fields_when_no_workflows_are_enabled():
    db = AsyncMock()
    db.execute.return_value = _RowsResult([])

    result = await get_ci_stats(db)

    assert result["total_runs"] == 0
    assert result["passed_runs"] == 0
    assert result["failed_runs"] == 0
    assert result["other_runs"] == 0


def test_ci_stats_contract_keeps_existing_fields_and_adds_build_counts():
    stats = CIStats.model_validate({
        "total_runs": 3,
        "passed_runs": 1,
        "failed_runs": 1,
        "other_runs": 1,
        "success_rate": 33.33,
        "avg_duration_seconds": None,
        "last_7_days": {"runs": 0, "success_rate": 0.0, "avg_duration_seconds": None},
    })

    assert stats.model_dump() == {
        "total_runs": 3,
        "passed_runs": 1,
        "failed_runs": 1,
        "other_runs": 1,
        "success_rate": 33.33,
        "avg_duration_seconds": None,
        "last_7_days": {"runs": 0, "success_rate": 0.0, "avg_duration_seconds": None},
    }
