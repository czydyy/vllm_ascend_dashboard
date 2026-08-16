"""Repair test-board rows synthesized from non-executed GitHub jobs.

Older versions of the parser created a failed test result when a skipped or
cancelled matrix job had no report artifact.  This migration is idempotent and
removes only rows linked to those explicit GitHub conclusions.  It is safe to
run again after the source-code fix has been deployed.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select

from infrastructure.db.base import SessionLocal
from infrastructure.persistence.models import CIJob, DailyFailureRecord
from infrastructure.persistence.models.test_board import FailureAnnotation, TestCase, TestRun
from tooling.analytics.test_health_calculator import TestHealthCalculator

NON_EXECUTED_CONCLUSIONS = ("skipped", "cancelled")


async def run() -> dict[str, int]:
    """Remove false test results and rebuild derived test-board counters."""

    async with SessionLocal() as db:
        non_executed_job_ids = {
            row[0]
            for row in (await db.execute(
                select(CIJob.job_id).where(CIJob.conclusion.in_(NON_EXECUTED_CONCLUSIONS))
            )).all()
        }
        false_runs = (await db.execute(
            select(TestRun.id, TestRun.test_case_id).where(
                TestRun.ci_job_id.in_(non_executed_job_ids)
            )
        )).all()
        false_run_ids = {row[0] for row in false_runs}
        affected_case_ids = {row[1] for row in false_runs}

        annotations_removed = 0
        runs_removed = 0
        if false_run_ids:
            annotations_result = await db.execute(
                delete(FailureAnnotation).where(FailureAnnotation.test_run_id.in_(false_run_ids))
            )
            runs_result = await db.execute(
                delete(TestRun).where(TestRun.id.in_(false_run_ids))
            )
            annotations_removed = annotations_result.rowcount or 0
            runs_removed = runs_result.rowcount or 0

        remaining_case_ids = {
            row[0]
            for row in (await db.execute(
                select(TestRun.test_case_id).where(TestRun.test_case_id.in_(affected_case_ids))
            )).all()
        }
        orphan_case_ids = affected_case_ids - remaining_case_ids
        orphan_result = await db.execute(
            delete(TestCase).where(TestCase.id.in_(orphan_case_ids))
        ) if orphan_case_ids else None

        # Restore lifetime counters for retained cases before the regular
        # health calculation rebuilds its rolling-window fields.
        runs_by_case: dict[int, list[TestRun]] = defaultdict(list)
        if remaining_case_ids:
            remaining_runs = (await db.execute(
                select(TestRun).where(TestRun.test_case_id.in_(remaining_case_ids)).order_by(
                    TestRun.test_case_id, TestRun.started_at, TestRun.id
                )
            )).scalars().all()
            for test_run in remaining_runs:
                runs_by_case[test_run.test_case_id].append(test_run)

        for case_id, runs in runs_by_case.items():
            case = await db.get(TestCase, case_id)
            if case is None:
                continue
            latest = runs[-1] if runs else None
            case.lifetime_runs = len(runs)
            case.lifetime_failures = sum(1 for item in runs if item.result == "failed")
            case.last_result = latest.result if latest else None
            case.last_run_at = latest.started_at if latest else None

        cancelled_job_ids = {
            row[0]
            for row in (await db.execute(
                select(CIJob.job_id).where(CIJob.conclusion == "cancelled")
            )).all()
        }
        daily_result = await db.execute(
            delete(DailyFailureRecord).where(DailyFailureRecord.job_id.in_(cancelled_job_ids))
        ) if cancelled_job_ids else None

        await db.commit()

        calculator = TestHealthCalculator(db)
        health_cases = await calculator.calculate_all_health_scores()
        await calculator.calculate_suite_snapshot()

        return {
            "test_runs_removed": runs_removed,
            "annotations_removed": annotations_removed,
            "orphan_test_cases_removed": (orphan_result.rowcount or 0) if orphan_result else 0,
            "cancelled_daily_failures_removed": (daily_result.rowcount or 0) if daily_result else 0,
            "health_cases_recalculated": health_cases,
        }


__all__ = ["run"]
