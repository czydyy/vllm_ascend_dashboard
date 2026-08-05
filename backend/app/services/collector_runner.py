"""
CollectorRunner：桥接 CollectorWorker 与具体采集逻辑。

从 collection_tasks 领取任务，根据 task_type 分发执行。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import text

from app.core.config import settings
from app.db.base import SessionLocal
from app.services.ci_collector import CICollector
from app.services.collector_base import CollectorWorker, TaskContext
from app.services.github_client import GitHubClient

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

        logger.info("Executing task %d type=%s generation=%d", ctx.task_id, task_type, ctx.lease_generation)

        # 后台续约
        renew_task = asyncio.create_task(self._renew_loop(ctx.task_id, ctx.lease_token, renew_fn))

        try:
            if task_type == "ci_sync":
                await self._run_ci_sync(ctx)
            elif task_type == "model_sync":
                await self._run_model_sync(ctx)
            else:
                logger.warning("Unknown task_type=%s for task %d", task_type, ctx.task_id)
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

    async def _run_ci_sync(self, ctx: TaskContext):
        """CI 数据同步。"""
        github = GitHubClient(settings.GITHUB_TOKEN)
        async with SessionLocal() as db:
            collector = CICollector(github, db)
            await collector.collect_workflow_runs(
                days_back=settings.CI_SYNC_DAYS_BACK,
                max_runs_per_workflow=settings.CI_SYNC_MAX_RUNS_PER_WORKFLOW,
            )

    async def _run_model_sync(self, ctx: TaskContext):
        """模型报告同步。"""
        from app.services.model_sync_service import sync_all_models
        await sync_all_models()
