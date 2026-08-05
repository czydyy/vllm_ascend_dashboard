"""
CollectorRunner：桥接 CollectorWorker 与具体采集逻辑。

读取 collection_tasks 中的任务参数，分发给现有的 CICollector 等。
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.db.base import SessionLocal
from app.services.ci_collector import CICollector
from app.services.collector_base import CollectorWorker, TaskContext
from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)


class CollectorRunner:
    """接管 CollectorWorker，将任务分发给具体的采集器。"""

    def __init__(self, worker: CollectorWorker):
        self.worker = worker

    async def run(self):
        """重写 _execute_with_lease，然后启动 worker 主循环。"""
        # Monkey-patch: 把 _execute_with_lease 替换为实际逻辑
        self.worker._execute_with_lease = self._execute_with_lease
        await self.worker.run()

    async def _execute_with_lease(self, ctx: TaskContext):
        """根据 task_type 执行具体采集，同时处理续约。"""
        import asyncio

        task_id = ctx.task_id
        lease_token = ctx.lease_token

        # 从 DB 读取任务详情
        from sqlalchemy import text

        async with SessionLocal() as db:
            result = await db.execute(
                text("SELECT task_type, task_params FROM collection_tasks WHERE id = :id"),
                {"id": task_id},
            )
            row = result.fetchone()
            if not row:
                logger.error("Task %d not found", task_id)
                return
            task_type, task_params = row

        logger.info("Executing task %d type=%s", task_id, task_type)

        try:
            # 启动续约协程
            renew_task = asyncio.create_task(self._renew_loop(task_id, lease_token))

            try:
                if task_type == "ci_sync":
                    await self._run_ci_sync(ctx)
                elif task_type == "model_sync":
                    await self._run_model_sync(ctx)
                elif task_type == "perf_sync":
                    await self._run_perf_sync(ctx)
                else:
                    logger.warning("Unknown task_type=%s for task %d", task_type, task_id)
            finally:
                renew_task.cancel()
                try:
                    await renew_task
                except asyncio.CancelledError:
                    pass

            # 标记完成
            await self.worker._complete_task(task_id, lease_token)
            logger.info("Task %d completed", task_id)

        except Exception as exc:
            logger.error("Task %d failed: %s", task_id, exc)
            await self.worker._fail_task(task_id, lease_token, str(exc), retry=True)

    async def _renew_loop(self, task_id: int, lease_token: str):
        """后台续约协程。"""
        import asyncio

        while True:
            await asyncio.sleep(self.worker._renew_interval)
            ok = await self.worker._renew_lease(task_id, lease_token)
            if not ok:
                logger.warning("Task %d lease renewal failed, token may be invalid", task_id)
                return

    # ── 具体采集逻辑 ──

    async def _run_ci_sync(self, ctx: TaskContext):
        """CI 数据同步。"""
        github = GitHubClient(settings.GITHUB_TOKEN)
        async with SessionLocal() as db:
            collector = CICollector(github, db)
            params = self._read_params(ctx)
            await collector.collect_workflow_runs(
                workflow_files=params.get("workflow_files"),
                days_back=params.get("days_back", 7),
                max_runs_per_workflow=params.get("max_runs", 100),
            )

    async def _run_model_sync(self, ctx: TaskContext):
        """模型报告同步。"""
        # 对接现有 model_sync_service
        from app.services.model_sync_service import sync_all_models
        await sync_all_models()

    async def _run_perf_sync(self, ctx: TaskContext):
        """性能数据同步。"""
        # 对接现有 performance parser + sync logic
        logger.info("Performance sync not yet implemented in collector runner")

    def _read_params(self, ctx: TaskContext) -> dict:
        """读取任务参数（简化：从 self.worker._task_contexts 获取 checkpoint）。"""
        return {}
