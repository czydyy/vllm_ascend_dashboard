"""
CollectorRunner：桥接 CollectorWorker 与具体采集逻辑。

从 collection_tasks 领取任务，根据 task_type 分发执行。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import text

from infrastructure.core.config import settings
from infrastructure.db.base import SessionLocal
from collector.ci import CICollector
from .worker import CollectorWorker, TaskContext
from infrastructure.clients.github_client import GitHubClient
from collector.pr_pipeline import PRPipelineCollector

logger = logging.getLogger(__name__)


class CollectorRunner:
    """将具体采集逻辑绑定到 CollectorWorker。"""

    def __init__(self, worker: CollectorWorker):
        self.worker = worker

    async def run(self):
        """启动 Collector，使用 run_with_executor 绑定具体逻辑。"""
        await self.worker.run_with_executor(self._execute_task)

    async def _execute_task(self, ctx: TaskContext, renew_fn):
        """根据 task_type 执行具体采集，同时后台续约。"""
        # 从 DB 读取任务详情
        async with SessionLocal() as db:
            result = await db.execute(
                text("SELECT task_type, task_params FROM collection_tasks WHERE id = :id"),
                {"id": ctx.task_id},
            )
            row = result.fetchone()
            if not row:
                logger.error("Task %d not found", ctx.task_id)
                return
            task_type, task_params = row
            if isinstance(task_params, str):
                task_params = json.loads(task_params)
            task_params = task_params or {}

        logger.info("Executing task %d type=%s generation=%d", ctx.task_id, task_type, ctx.lease_generation)

        # 后台续约
        renew_task = asyncio.create_task(self._renew_loop(ctx.task_id, ctx.lease_token, renew_fn))

        try:
            if task_type == "ci_sync":
                await self._run_ci_sync(ctx, task_params)
            elif task_type == "pr_sync":
                await self._run_pr_sync(ctx, task_params)
            elif task_type == "pr_historical_sync":
                await self._run_pr_historical_sync(ctx, task_params)
            elif task_type == "failure_analysis":
                await self._run_failure_analysis(ctx, task_params)
            elif task_type == "issues_derivation":
                await self._run_issues_derivation(ctx)
            elif task_type == "model_sync":
                await self._run_model_sync(ctx, task_params)
            elif task_type == "code_metrics_collect":
                await self._run_code_metrics_collect(ctx, task_params)
            elif task_type == "code_heatmap_sync":
                await self._run_code_heatmap_sync(ctx, task_params)
            elif task_type == "resource_metrics_collect":
                await self._run_resource_metrics_collect(ctx)
            elif task_type == "resource_metrics_cleanup":
                await self._run_resource_metrics_cleanup(ctx)
            else:
                raise ValueError(f"Unsupported collection task type: {task_type}")
        finally:
            renew_task.cancel()
            try:
                await renew_task
            except asyncio.CancelledError:
                pass

    async def _renew_loop(self, task_id: int, token: str, renew_fn):
        """后台续约协程。"""
        while True:
            await asyncio.sleep(self.worker._renew_interval)
            ok = await renew_fn(task_id, token)
            if not ok:
                logger.warning("Task %d lease renewal failed", task_id)
                return

    async def _run_ci_sync(self, ctx: TaskContext, task_params: dict):
        """CI 数据同步。"""
        github = GitHubClient(settings.GITHUB_TOKEN)
        try:
            async with SessionLocal() as db:
                collector = CICollector(github, db)
                await collector.collect_workflow_runs(
                    days_back=int(task_params.get("days_back", settings.CI_SYNC_DAYS_BACK)),
                    max_runs_per_workflow=int(task_params.get("max_runs", settings.CI_SYNC_MAX_RUNS_PER_WORKFLOW)),
                    force_full_refresh=bool(task_params.get("force_full_refresh", False)),
                )
        finally:
            await github.close()

    async def _run_model_sync(self, ctx: TaskContext, task_params: dict):
        """模型报告同步。"""
        from shared.services.model_sync_service import ModelSyncService

        github = GitHubClient(settings.GITHUB_TOKEN)
        try:
            async with SessionLocal() as db:
                service = ModelSyncService(db, github)
                total, collected = await service.sync_all_enabled_configs(
                    days_back=int(task_params.get("days_back", settings.MODEL_SYNC_DAYS_BACK)),
                    runs_limit=int(task_params.get("runs_limit", settings.MODEL_SYNC_RUNS_LIMIT)),
                )
                logger.info(
                    "Model sync task %d completed: %d configs, %d reports",
                    ctx.task_id,
                    total,
                    collected,
                )
        finally:
            await github.close()

    async def _run_failure_analysis(self, ctx: TaskContext, task_params: dict):
        """Run one failure analysis from the durable task queue."""
        from shared.services.failure_analysis import FailureAnalysisService

        job_id = int(task_params["job_id"])
        force = bool(task_params.get("force", False))
        triggered_by = str(task_params.get("triggered_by", "manual"))
        async with SessionLocal() as db:
            await FailureAnalysisService().analyze_failed_job(
                job_id=job_id,
                db=db,
                force=force,
                triggered_by=triggered_by,
            )

    async def _run_code_metrics_collect(self, ctx: TaskContext, task_params: dict):
        """Run local code-metrics tools only in the Collector execution role."""
        from collector.code_metrics import CodeMetricsCollector

        async with SessionLocal() as db:
            result = await CodeMetricsCollector(db).collect(
                branch=str(task_params.get("branch", "main"))
            )
        logger.info("Code metrics task %d completed: %s", ctx.task_id, result)

    async def _run_code_heatmap_sync(self, ctx: TaskContext, task_params: dict):
        """Synchronize the code heatmap via GitHub from the Collector role."""
        from collector.heatmap import sync_heatmap_from_github

        github = GitHubClient(settings.GITHUB_TOKEN)
        try:
            async with SessionLocal() as db:
                result = await sync_heatmap_from_github(
                    db,
                    github,
                    settings.GITHUB_OWNER,
                    settings.GITHUB_REPO,
                    days=int(task_params.get("days", 30)),
                )
            logger.info("Code heatmap task %d completed: %s", ctx.task_id, result)
        finally:
            await github.close()

    async def _run_resource_metrics_collect(self, ctx: TaskContext):
        """Collect node and NPU metrics from the Collector execution role."""
        from shared.services.alert_evaluator import AlertEvaluator
        from collector.resource_metrics import ResourceMetricsCollector

        async with SessionLocal() as db:
            count = await ResourceMetricsCollector(db).collect_snapshot()
            alerts = await AlertEvaluator(db).evaluate_all_rules()
        logger.info(
            "Resource metrics task %d completed: clusters=%d alerts=%d",
            ctx.task_id,
            count,
            alerts,
        )

    async def _run_resource_metrics_cleanup(self, ctx: TaskContext):
        """Delete expired resource metrics from the Collector execution role."""
        from collector.resource_metrics import ResourceMetricsCollector

        async with SessionLocal() as db:
            deleted = await ResourceMetricsCollector(db).cleanup_old_metrics()
        logger.info("Resource metrics cleanup task %d deleted %d rows", ctx.task_id, deleted)

    async def _run_issues_derivation(self, ctx: TaskContext):
        """Derive test-board issue counts from durable worker execution."""
        from shared.services.issues_found_derivator import IssuesFoundDerivator

        async with SessionLocal() as db:
            result = await IssuesFoundDerivator(db).derive_all()
            logger.info("issues derivation task %d completed: %s", ctx.task_id, result)

    async def _run_pr_sync(self, ctx: TaskContext, task_params: dict):
        """Synchronize pull-request pipeline data from GitHub."""
        github = GitHubClient(settings.GITHUB_TOKEN)
        try:
            async with SessionLocal() as db:
                collector = PRPipelineCollector(github, db)
                await collector.collect_prs(
                    settings.GITHUB_OWNER,
                    settings.GITHUB_REPO,
                    days_back=int(task_params.get("days_back", 7)),
                )
        finally:
            await github.close()

    async def _run_pr_historical_sync(self, ctx: TaskContext, task_params: dict):
        """Collect historical PR data; this can be long-running and rate-limited."""
        from collector.pr_pipeline_historical import PRPipelineHistoricalCollector

        github = GitHubClient(settings.GITHUB_TOKEN)
        try:
            async with SessionLocal() as db:
                result = await PRPipelineHistoricalCollector(github, db).collect_historical(
                    settings.GITHUB_OWNER,
                    settings.GITHUB_REPO,
                    phases=list(task_params.get("phases", ["A", "B"])),
                    months_back=int(task_params.get("months_back", 3)),
                )
            logger.info("Historical PR task %d completed: %s", ctx.task_id, result)
        finally:
            await github.close()
