"""
数据同步定时任务调度器
使用 APScheduler 实现定时数据采集
"""
import asyncio
import logging
from datetime import UTC, datetime, date, timedelta, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import bindparam, text

from infrastructure.core.config import settings
from infrastructure.db.base import SessionLocal
from infrastructure.clients.github_client import GitHubClient

logger = logging.getLogger(__name__)


async def _read_config_async(config_key: str) -> dict | None:
    """从数据库读取配置（仅限异步上下文调用）。"""
    try:
        from sqlalchemy import select as sa_select
        from infrastructure.persistence.models import ProjectDashboardConfig
        async with SessionLocal() as db:
            stmt = sa_select(ProjectDashboardConfig).where(
                ProjectDashboardConfig.config_key == config_key
            )
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            if row and row.config_value:
                return dict(row.config_value)
            return None
    except Exception as e:
        logger.warning(f"Failed to read config '{config_key}' from database: {e}")
        return None


class DataSyncScheduler:
    """
    数据同步定时任务调度器
    
    功能：
    - 定时同步 CI 数据（可配置间隔）
    - 手动触发同步
    - 任务执行监控
    """

    def __init__(self):
        """初始化调度器（不读 DB，DB 配置由 apply_db_config_overrides 异步加载）"""
        self._timezone = 'Asia/Shanghai'

        self.scheduler = AsyncIOScheduler(
            timezone=self._timezone,
            job_defaults={
                'coalesce': True,  # 合并错过的执行
                'max_instances': 1,  # 同一任务最多只有 1 个实例运行
                'misfire_grace_time': 60,  # 错过执行的容忍时间（秒）
            }
        )

        # 任务执行监听
        self.scheduler.add_listener(
            self._job_event_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        self.github_client: GitHubClient | None = None
        self._initialized = False

        logger.info("DataSyncScheduler initialized")

    def _job_event_listener(self, event):
        """任务执行事件监听"""
        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
        else:
            logger.info(f"Job {event.job_id} executed successfully at {datetime.now()}")

    def start(self) -> None:
        """启动调度器"""
        logger.info("=" * 60)
        logger.info("SCHEDULER STARTING - Adding scheduled jobs")
        logger.info("=" * 60)
        
        if not self._initialized:
            self._initialize_github_client()

        # CI 数据同步任务 - 可配置间隔（默认 720 分钟 = 12 小时）
        sync_interval_minutes = getattr(settings, 'CI_SYNC_INTERVAL_MINUTES', 720)

        try:
            self.scheduler.add_job(
                self._sync_ci_data_job,
                trigger=IntervalTrigger(minutes=sync_interval_minutes),
                id="ci_data_sync",
                name="CI Data Sync",
                replace_existing=True,
            )
            logger.info(f"[1/4] CI data sync scheduled every {sync_interval_minutes} minutes")
        except Exception as e:
            logger.error(f"Failed to add CI data sync job: {e}", exc_info=True)

        # Project Dashboard Git 仓库缓存更新任务 - 每小时更新一次
        cache_update_interval = getattr(settings, 'PROJECT_DASHBOARD_CACHE_INTERVAL_MINUTES', 60)
        try:
            self.scheduler.add_job(
                self._update_project_dashboard_cache_job,
                trigger=IntervalTrigger(minutes=cache_update_interval),
                id="project_dashboard_cache_update",
                name="Project Dashboard Cache Update",
                replace_existing=True,
            )
            logger.info(f"[2/4] Project dashboard cache update scheduled every {cache_update_interval} minutes")
        except Exception as e:
            logger.error(f"Failed to add project dashboard cache update job: {e}", exc_info=True)

        # 模型报告同步任务 - 可配置间隔（默认 60 分钟）
        model_sync_interval = getattr(settings, 'MODEL_SYNC_INTERVAL_MINUTES', 60)
        try:
            self.scheduler.add_job(
                self._sync_model_reports_job,
                trigger=IntervalTrigger(minutes=model_sync_interval),
                id="model_report_sync",
                name="Model Report Sync",
                replace_existing=True,
            )
            logger.info(f"[3/4] Model report sync scheduled every {model_sync_interval} minutes")
        except Exception as e:
            logger.error(f"Failed to add model report sync job: {e}", exc_info=True)

        # 每日总结生成任务 - 每天早上 8 点执行（可配置）
        try:
            from apscheduler.triggers.cron import CronTrigger

            cron_hour = getattr(settings, 'DAILY_SUMMARY_CRON_HOUR', 8)
            cron_minute = getattr(settings, 'DAILY_SUMMARY_CRON_MINUTE', 0)
            enabled = getattr(settings, 'DAILY_SUMMARY_ENABLED', True)

            if enabled:
                self.scheduler.add_job(
                    self._generate_daily_summary_job,
                    trigger=CronTrigger(hour=cron_hour, minute=cron_minute, timezone=self._timezone),
                    id="daily_summary_task",
                    name="Generate Daily Summary",
                    replace_existing=True,
                )
                logger.info(f"[4/4] Daily summary generation scheduled at {cron_hour}:{cron_minute:02d} {self._timezone} (enabled={enabled})")
            else:
                logger.info(f"[4/4] Daily summary generation DISABLED (enabled={enabled})")
        except Exception as e:
            logger.error(f"Failed to add daily summary job: {e}", exc_info=True)

        # 启动调度器
        if not self.scheduler.running:
            try:
                self.scheduler.start()
                logger.info("=" * 60)
                logger.info("SCHEDULER STARTED SUCCESSFULLY")
                jobs = self.scheduler.get_jobs()
                logger.info(f"Total jobs scheduled: {len(jobs)}")
                for job in jobs:
                    logger.info(f"  - {job.id}: {job.name}, next_run={job.next_run_time}")
                logger.info("=" * 60)
            except Exception as e:
                logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        else:
            logger.info("Scheduler already running")

        # 心跳任务 — 让独立 scheduler 进程的存活状态对 API 进程可见
        # （API 进程内的 APScheduler 为空，无法直接感知独立 scheduler）
        try:
            self.scheduler.add_job(
                self.write_heartbeat,
                trigger=IntervalTrigger(seconds=20),
                id="scheduler_heartbeat",
                name="Scheduler Heartbeat",
                replace_existing=True,
            )
            logger.info("Scheduler heartbeat scheduled every 20s")
        except Exception as e:
            logger.error(f"Failed to add heartbeat job: {e}", exc_info=True)

        # Control-plane events are durable MySQL commands emitted by the API.
        # They replace cross-process mutation of this APScheduler instance.
        try:
            self.scheduler.add_job(
                self._consume_control_events,
                trigger=IntervalTrigger(seconds=5),
                id="scheduler_control_plane",
                name="Scheduler Control Plane",
                replace_existing=True,
            )
        except Exception as e:
            logger.error("Failed to add control-plane consumer: %s", e, exc_info=True)

        # NPU 指标采集任务 - 默认每 1 分钟执行
        try:
            metrics_interval = getattr(settings, 'RESOURCE_METRICS_INTERVAL_MINUTES', 1)

            self.scheduler.add_job(
                self._collect_resource_metrics_job,
                trigger=IntervalTrigger(minutes=metrics_interval),
                id="resource_metrics_collect",
                name="Resource Metrics Collect",
                replace_existing=True,
            )
            logger.info(f"Resource metrics collection scheduled every {metrics_interval} minutes")
        except Exception as e:
            logger.error(f"Failed to add resource metrics collection job: {e}", exc_info=True)

        # NPU 指标数据清理任务 - 每天凌晨 00:00 执行
        try:
            from apscheduler.triggers.cron import CronTrigger
            self.scheduler.add_job(
                self._cleanup_resource_metrics_job,
                trigger=CronTrigger(hour=0, minute=0, timezone=self._timezone),
                id="resource_metrics_cleanup",
                name="Resource Metrics Cleanup",
                replace_existing=True,
            )
            logger.info(f"Resource metrics cleanup scheduled at 00:00 {self._timezone}")
        except Exception as e:
            logger.error(f"Failed to add resource metrics cleanup job: {e}", exc_info=True)

        # 失败分析兜底已移除 — 仅由 CI sync 后触发 _analyze_failed_jobs

        # 每日运行报告邮件推送任务 - 默认 8:30 执行（DB 中的时间由 apply_db_config_overrides 覆盖）
        try:
            from apscheduler.triggers.cron import CronTrigger

            report_enabled = getattr(settings, 'REPORT_ENABLED', True)
            report_hour = getattr(settings, 'REPORT_SCHEDULE_HOUR', 8)
            report_minute = getattr(settings, 'REPORT_SCHEDULE_MINUTE', 30)
            local_tz = self._timezone

            if report_enabled:
                self.scheduler.add_job(
                    self._send_daily_report_job,
                    trigger=CronTrigger(hour=report_hour, minute=report_minute, timezone=local_tz),
                    id="daily_report_task",
                    name="Daily Report Email",
                    replace_existing=True,
                )
                logger.info(f"Daily report email scheduled at {report_hour}:{report_minute:02d} {local_tz} (enabled={report_enabled})")
            else:
                logger.info(f"Daily report email DISABLED (enabled={report_enabled})")
        except Exception as e:
            logger.error(f"Failed to add daily report job: {e}", exc_info=True)

        # CI 失败分析已移除 — 仅由 _sync_ci_data_job 中 _analyze_failed_jobs 触发

        pr_pipeline_interval = getattr(settings, 'PR_PIPELINE_SYNC_INTERVAL_MINUTES', 30)
        try:
            self.scheduler.add_job(
                self._sync_pr_pipeline_job,
                trigger=IntervalTrigger(minutes=pr_pipeline_interval),
                id="pr_pipeline_sync",
                name="PR Pipeline Sync",
                replace_existing=True,
            )
            logger.info(f"PR pipeline sync scheduled every {pr_pipeline_interval} minutes")
        except Exception as e:
            logger.error(f"Failed to add PR pipeline sync job: {e}", exc_info=True)

        try:
            self.scheduler.add_job(
                self._cleanup_logs_job,
                trigger=IntervalTrigger(hours=6),
                id="cleanup_logs",
                name="Cleanup Expired Logs and Tokens",
                replace_existing=True,
            )
            logger.info("Log cleanup scheduled every 6 hours")
        except Exception as e:
            logger.error(f"Failed to add log cleanup job: {e}", exc_info=True)

        test_board_interval = getattr(settings, 'TEST_BOARD_SYNC_INTERVAL_MINUTES', 120)
        try:
            self.scheduler.add_job(
                self._parse_test_results_job,
                trigger=IntervalTrigger(minutes=test_board_interval),
                id="test_result_parse",
                name="Test Board Result Parse",
                replace_existing=True,
            )
            logger.info(f"Test board result parse scheduled every {test_board_interval} minutes")
        except Exception as e:
            logger.error(f"Failed to add test board result parse job: {e}", exc_info=True)

        try:
            self.scheduler.add_job(
                self._calc_test_health_job,
                trigger=IntervalTrigger(minutes=test_board_interval + 30),
                id="test_health_calc",
                name="Test Board Health Calc",
                replace_existing=True,
            )
            logger.info(f"Test board health calc scheduled every {test_board_interval + 30} minutes")
        except Exception as e:
            logger.error(f"Failed to add test health calc job: {e}", exc_info=True)

        try:
            self.scheduler.add_job(
                self._snapshot_test_suites_job,
                trigger=IntervalTrigger(hours=6),
                id="test_suite_snapshot",
                name="Test Board Suite Snapshot",
                replace_existing=True,
            )
            logger.info("Test board suite snapshot scheduled every 6 hours")
        except Exception as e:
            logger.error(f"Failed to add test suite snapshot job: {e}", exc_info=True)

        try:
            from apscheduler.triggers.cron import CronTrigger
            self.scheduler.add_job(
                self._cleanup_test_runs_job,
                trigger=CronTrigger(hour=2, minute=0, timezone=self._timezone),
                id="cleanup_test_runs",
                name="Test Board Run Cleanup",
                replace_existing=True,
            )
            logger.info(f"Test board run cleanup scheduled at 02:00 {self._timezone}")
        except Exception as e:
            logger.error(f"Failed to add test board cleanup job: {e}", exc_info=True)

        # 已退出测试用例物理清理 — 每日凌晨 02:30 删除超过 STALE_CASE_DELETE_DAYS 天未运行的用例
        try:
            from apscheduler.triggers.cron import CronTrigger
            self.scheduler.add_job(
                self._cleanup_stale_cases_job,
                trigger=CronTrigger(hour=2, minute=30, timezone=self._timezone),
                id="cleanup_stale_cases",
                name="Test Board Stale Case Cleanup",
                replace_existing=True,
            )
            logger.info(f"Test board stale case cleanup scheduled at 02:30 {self._timezone}")
        except Exception as e:
            logger.error(f"Failed to add stale case cleanup job: {e}", exc_info=True)

        # 上游支持矩阵同步任务 - 每日同步
        if getattr(settings, 'SUPPORT_MATRIX_SYNC_ENABLED', True):
            try:
                from apscheduler.triggers.cron import CronTrigger
                sync_hour = getattr(settings, 'SUPPORT_MATRIX_SYNC_CRON_HOUR', 6)
                sync_minute = getattr(settings, 'SUPPORT_MATRIX_SYNC_CRON_MINUTE', 0)
                self.scheduler.add_job(
                    self._sync_support_matrix_job,
                    trigger=CronTrigger(hour=sync_hour, minute=sync_minute, timezone=self._timezone),
                    id="support_matrix_sync",
                    name="Sync Upstream Support Matrix",
                    replace_existing=True,
                )
                logger.info(f"Support matrix sync scheduled at {sync_hour}:{sync_minute:02d} {self._timezone}")
            except Exception as e:
                logger.error(f"Failed to add support matrix sync job: {e}", exc_info=True)

        # 代码度量定时清理
        try:
            from apscheduler.triggers.cron import CronTrigger
            self.scheduler.add_job(
                self._cleanup_code_metrics_job,
                trigger=CronTrigger(hour=3, minute=0, timezone=self._timezone),
                id="code_metrics_cleanup",
                name="Code Metrics Cleanup",
                replace_existing=True,
            )
            logger.info(f"Code metrics cleanup scheduled at 03:00 daily")
        except Exception as e:
            logger.error(f"Failed to add code metrics cleanup job: {e}")

        # 代码度量热力图同步
        try:
            from apscheduler.triggers.cron import CronTrigger
            self.scheduler.add_job(
                self._sync_heatmap_job,
                trigger=CronTrigger(hour=4, minute=0, timezone=self._timezone),
                id="code_metrics_heatmap_sync",
                name="Code Metrics Heatmap Sync",
                replace_existing=True,
            )
            logger.info(f"Code metrics heatmap sync scheduled at 04:00 daily")
        except Exception as e:
            logger.error(f"Failed to add heatmap sync job: {e}")

        # 代码度量本地采集
        try:
            from apscheduler.triggers.cron import CronTrigger
            self.scheduler.add_job(
                self._collect_code_metrics_job,
                trigger=CronTrigger(hour=5, minute=0, timezone=self._timezone),
                id="code_metrics_collect",
                name="Code Metrics Collection",
                replace_existing=True,
            )
            logger.info(f"Code metrics collection scheduled at 05:00 daily")
        except Exception as e:
            logger.error(f"Failed to add code metrics collection job: {e}")

    async def apply_db_config_overrides(self) -> None:
        """从数据库读取调度配置，覆盖默认值（异步，仅在事件循环内调用）。

        应在 start() 之后、事件循环运行期间调用。
        对 aiomysql 安全 —— 使用当前事件循环，不会创建新循环。
        """
        try:
            runtime_config = await _read_config_async("scheduler_runtime_config")
            if runtime_config:
                field_map = {
                    "ci_sync_interval_minutes": "CI_SYNC_INTERVAL_MINUTES",
                    "ci_sync_days_back": "CI_SYNC_DAYS_BACK",
                    "ci_sync_max_runs_per_workflow": "CI_SYNC_MAX_RUNS_PER_WORKFLOW",
                    "ci_sync_force_full_refresh": "CI_SYNC_FORCE_FULL_REFRESH",
                    "model_sync_interval_minutes": "MODEL_SYNC_INTERVAL_MINUTES",
                    "model_sync_days_back": "MODEL_SYNC_DAYS_BACK",
                    "model_sync_runs_limit": "MODEL_SYNC_RUNS_LIMIT",
                    "project_dashboard_cache_interval_minutes": "PROJECT_DASHBOARD_CACHE_INTERVAL_MINUTES",
                    "data_retention_days": "DATA_RETENTION_DAYS",
                }
                for config_key, setting_name in field_map.items():
                    if config_key in runtime_config:
                        setattr(settings, setting_name, runtime_config[config_key])

                self.scheduler.add_job(
                    self._sync_ci_data_job,
                    trigger=IntervalTrigger(minutes=settings.CI_SYNC_INTERVAL_MINUTES),
                    id="ci_data_sync",
                    name="CI Data Sync",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    self._update_project_dashboard_cache_job,
                    trigger=IntervalTrigger(
                        minutes=settings.PROJECT_DASHBOARD_CACHE_INTERVAL_MINUTES
                    ),
                    id="project_dashboard_cache_update",
                    name="Project Dashboard Cache Update",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    self._sync_model_reports_job,
                    trigger=IntervalTrigger(minutes=settings.MODEL_SYNC_INTERVAL_MINUTES),
                    id="model_report_sync",
                    name="Model Report Sync",
                    replace_existing=True,
                )
        except Exception as e:
            logger.warning("Failed to apply scheduler runtime config: %s", e)

        try:
            schedule_config = await _read_config_async('daily_summary_schedule')
            if schedule_config:
                self._timezone = schedule_config.get('timezone', 'Asia/Shanghai')
                # 更新时区（需要重建 cron 任务）
                if self._timezone != 'Asia/Shanghai':
                    self.scheduler.configure(timezone=self._timezone)
                    logger.info(f"Applied timezone from DB: {self._timezone}")
        except Exception as e:
            logger.warning(f"Failed to apply DB timezone: {e}")

        try:
            report_config = await _read_config_async('daily_report_config')
            if report_config:
                hour = report_config.get('report_schedule_hour')
                minute = report_config.get('report_schedule_minute')
                if hour is not None and minute is not None:
                    self.update_report_schedule(
                        enabled=report_config.get('report_enabled', True),
                        cron_hour=int(hour),
                        cron_minute=int(minute),
                    )
                    logger.info(f"Applied report schedule from DB: {hour}:{minute:02d}")
        except Exception as e:
            logger.warning(f"Failed to apply DB report schedule: {e}")

        try:
            metrics_config = await _read_config_async('resource_metrics_config')
            if metrics_config and 'interval_minutes' in metrics_config:
                self.update_resource_metrics_schedule(int(metrics_config['interval_minutes']))
        except Exception as e:
            logger.warning(f"Failed to apply DB metrics interval: {e}")

    async def _consume_control_events(self) -> None:
        """Acknowledge durable API commands, then reload this process's schedule."""
        try:
            async with SessionLocal() as db:
                async with db.begin():
                    result = await db.execute(
                        text(
                            """
                            SELECT event_id FROM control_outbox
                            WHERE processed_at IS NULL
                              AND aggregate_type = 'scheduler'
                              AND event_type = 'scheduler.config.reload'
                            ORDER BY created_at
                            LIMIT 25 FOR UPDATE SKIP LOCKED
                            """
                        )
                    )
                    event_ids = [row[0] for row in result.fetchall()]
                    if event_ids:
                        await db.execute(
                            text(
                                "UPDATE control_outbox SET processed_at = NOW() "
                                "WHERE event_id IN :event_ids"
                            ).bindparams(bindparam("event_ids", expanding=True)),
                            {"event_ids": event_ids},
                        )
            if event_ids:
                await self.apply_db_config_overrides()
                logger.info("Applied %d scheduler control-plane events", len(event_ids))
        except Exception as e:
            logger.warning("Scheduler control-plane poll failed: %s", e)

    def update_report_schedule(
        self, enabled: bool = True, cron_hour: int = 8, cron_minute: int = 30
    ):
        """动态更新每日报告邮件定时任务"""
        from apscheduler.triggers.cron import CronTrigger

        try:
            if enabled:
                self.scheduler.add_job(
                    self._send_daily_report_job,
                    trigger=CronTrigger(hour=cron_hour, minute=cron_minute, timezone=self.scheduler.timezone),
                    id="daily_report_task",
                    name="Daily Report Email",
                    replace_existing=True,
                )
                logger.info(f"Daily report schedule updated: {cron_hour}:{cron_minute:02d}")
            else:
                try:
                    self.scheduler.remove_job('daily_report_task')
                except Exception:
                    pass
                logger.info("Daily report task disabled")
        except Exception as e:
            logger.error(f"Failed to update daily report schedule: {e}", exc_info=True)

    # /status 接口向用户展示的 job id —— 心跳需快照这些 job 的 next_run_time
    _HEARTBEAT_TRACKED_JOBS = (
        "ci_data_sync",
        "model_report_sync",
        "project_dashboard_cache_update",
        "daily_summary_task",
    )

    async def write_heartbeat(self, *, force_running: bool | None = None) -> None:
        """将当前调度器状态写入 DB 心跳表，供 API 进程读取。

        独立 scheduler 容器每 20s 调用一次；关闭前以 force_running=False 再调一次，
        使 API 进程能立即感知调度器已停止（无需等待心跳过期）。
        """
        import os

        from infrastructure.persistence.models import SchedulerHeartbeat

        running = bool(self.scheduler.running) if force_running is None else force_running
        jobs_payload: dict[str, dict] = {}
        for job_id in self._HEARTBEAT_TRACKED_JOBS:
            job = self.scheduler.get_job(job_id)
            jobs_payload[job_id] = {
                "name": job.name if job else None,
                "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
            }

        try:
            async with SessionLocal() as db:
                row = await db.get(SchedulerHeartbeat, 1)
                if row is None:
                    row = SchedulerHeartbeat(id=1)
                    db.add(row)
                row.running = running
                row.jobs = jobs_payload
                row.pid = os.getpid()
                row.updated_at = datetime.now(UTC)
                await db.commit()
        except Exception as e:
            # 心跳失败不应影响调度器主循环（如 DB 短暂抖动、表尚未由 backend init_db 建好）
            logger.warning(f"Heartbeat write failed (non-fatal): {e}")

    def stop(self) -> None:
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("DataSyncScheduler stopped")

        # 注意：这里不能直接 await 关闭 GitHub 客户端
        # 需要在应用生命周期管理中使用 async close() 方法
        if self.github_client:
            logger.info("GitHub client will be closed on next cleanup")

    async def close(self) -> None:
        """关闭调度器并清理资源（异步版本）"""
        # 关闭前写入最终心跳（running=False），让 API 进程立即感知调度器已停止
        try:
            await self.write_heartbeat(force_running=False)
        except Exception as e:
            logger.warning(f"Final heartbeat write failed (non-fatal): {e}")
        self.stop()
        if self.github_client:
            await self.github_client.close()
            self.github_client = None
            self._initialized = False
        logger.info("DataSyncScheduler resources cleaned up")

    def _initialize_github_client(self) -> None:
        """初始化 GitHub 客户端"""
        if not settings.GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not configured, GitHub API calls will fail")

        self.github_client = GitHubClient(
            token=settings.GITHUB_TOKEN,
            owner=settings.GITHUB_OWNER,
            repo=settings.GITHUB_REPO,
        )
        self._initialized = True

    async def _snapshot_nightly_configs(self, db) -> int:
        """从 vllm-ascend 各活跃分支拉取 nightly_config.yaml 快照到 nightly_test_cases"""
        from datetime import date as date_type

        from sqlalchemy import select

        from infrastructure.persistence.models import NightlyTestCase
        from tooling.parsers.nightly_config_parser import NightlyConfigParser, load_model_fo_map

        fo_map = load_model_fo_map()
        parser = NightlyConfigParser()
        if not parser.is_available:
            logger.warning("nightly_config.yaml not available, skip snapshot")
            return 0

        today = date_type.today()
        branches = parser.get_active_branches()
        # 只保留 main + release 分支
        target_branches = ["main"] + [b for b in branches if b.startswith("releases/")]

        total = 0
        for branch in target_branches:
            if not parser.checkout_branch(branch):
                continue
            cases = parser.parse(report_date=str(today), source_branch=branch)
            if not cases:
                continue

            for c in cases:
                # 检查是否已存在
                stmt = select(NightlyTestCase).where(
                    NightlyTestCase.report_date == today,
                    NightlyTestCase.source_branch == branch,
                    NightlyTestCase.workflow_name == c.workflow,
                    NightlyTestCase.job_name == c.name,
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                fo_value = fo_map.get(c.model_path) or fo_map.get(c.model_path.split("/")[-1]) or fo_map.get(c.model_path.rsplit(".", 1)[0] if "." in c.model_path else c.model_path, "")
                if existing:
                    if not existing.model_fo and fo_value:
                        existing.model_fo = fo_value
                else:
                    db.add(NightlyTestCase(
                        report_date=today,
                        source_branch=branch,
                        workflow_name=c.workflow,
                        job_name=c.name,
                        display_name=c.name,
                        test_model=c.model_path,
                        model_fo=fo_value,
                        deployment_type=c.deployment,
                    ))
                total += 1

        if total > 0:
            await db.commit()
        logger.info(f"Snapshot nightly config: {total} new entries across {len(target_branches)} branches")
        return total

    async def _populate_daily_failure_records(self, db) -> int:
        """物化每日失败记录：从 CIJob 提取分支，匹配对应分支的 NightlyTestCase 快照"""
        import re
        from datetime import timedelta, timezone

        from sqlalchemy import select

        from infrastructure.persistence.models import CIJob, DailyFailureRecord, NightlyTestCase

        beijing_tz = timezone(timedelta(hours=8))
        now_utc = datetime.now(UTC)
        cutoff = now_utc - timedelta(days=14)

        stmt = select(CIJob).where(
            CIJob.started_at >= cutoff,
            CIJob.conclusion.in_(["failure", "cancelled"]),
        )
        result = await db.execute(stmt)
        failed_jobs = result.scalars().all()

        # 加载 NightlyTestCase 快照，按 (report_date, source_branch, workflow_name, job_name) 索引
        tc_stmt = select(NightlyTestCase)
        tc_result = await db.execute(tc_stmt)
        tc_map: dict[tuple[str, str, str, str], NightlyTestCase] = {}
        for tc in tc_result.scalars().all():
            key = (str(tc.report_date), tc.source_branch, tc.workflow_name, tc.job_name)
            tc_map[key] = tc

        existing_stmt = select(DailyFailureRecord)
        existing_result = await db.execute(existing_stmt)
        existing_keys: set[tuple[str, str, str, str]] = set()
        for rec in existing_result.scalars().all():
            existing_keys.add((str(rec.report_date), rec.source_branch, rec.workflow_name, rec.job_name))

        # 分支名提取正则：job_name 格式如 "single-node (main, ...)" 或 "double-node (releases/v0.23.0, ...)"
        branch_re = re.compile(r'^\S+\s+\(([^,]+),')

        new_count = 0
        for job in failed_jobs:
            started = job.started_at
            if not started:
                continue
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            beijing_date = started.astimezone(beijing_tz).strftime("%Y-%m-%d")

            # 提取分支名
            branch = "main"
            m = branch_re.match(job.job_name) if job.job_name else None
            if m:
                branch = m.group(1)

            key = (beijing_date, branch, job.workflow_name, job.job_name)
            if key in existing_keys:
                continue

            # 匹配：CI job_name 末尾是 config 文件名（如 xx.yaml），
            # nightly_test_cases.test_model 存的就是 config_file_path
            tc = None
            for tc_key, tc_val in tc_map.items():
                tc_date, tc_branch, tc_wf, tc_job = tc_key
                if tc_date == beijing_date and tc_wf == job.workflow_name:
                    if (tc_val.test_model and tc_val.test_model in job.job_name) or tc_job in job.job_name:
                        tc = tc_val
                        break

            # 只保留 nightly_config.yaml 中定义的测试用例，
            # 跳过 Build image / Export env / clear-logs 等基础设施 job
            if not tc:
                continue

            github_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}/actions/runs/{job.run_id}/job/{job.job_id}" if job.job_id else None

            record = DailyFailureRecord(
                report_date=beijing_date,
                source_branch=branch,
                workflow_name=job.workflow_name,
                job_name=job.job_name,
                run_id=job.run_id,
                job_id=job.job_id,
                conclusion=job.conclusion,
                started_at=job.started_at,
                completed_at=job.completed_at,
                duration_seconds=job.duration_seconds,
                hardware=job.hardware,
                display_name=tc.display_name if tc else None,
                test_model=tc.test_model if tc else None,
                model_fo=tc.model_fo if tc else None,
                owner=tc.owner if tc else None,
                deployment_type=tc.deployment_type if tc else None,
                processing_status="未处理",
                github_job_url=github_url,
            )
            db.add(record)
            existing_keys.add(key)
            new_count += 1

        if new_count > 0:
            await db.commit()
        return new_count

    async def run_ci_post_sync(self, db) -> None:
        """CI 采集完成后的数据管线，scheduler 全量路径与 COLLECTOR_MODE collector 共用。

        步骤：刷新 WorkflowConfig.last_sync_at → 更新本地仓库缓存（供 nightly_config.yaml
        快照）→ 快照各分支用例配置 → 物化每日失败记录。

        COLLECTOR_MODE 下 scheduler 仅创建采集任务后返回，采集由 collector 执行；
        若不在 collector 侧补跑这些步骤，last_sync_at 不更新、用例快照停滞、
        每日失败记录不再增长（这正是 2026-08 失败用例跟踪断数据的根因之一）。

        每步独立、best-effort；失败时记 ERROR（而非旧版的 non-fatal WARNING），
        避免像 source_branch 缺列那样被静默吞掉数天无人察觉。
        """
        from datetime import UTC

        # 1. 更新所有启用 workflow 的 last_sync_at
        try:
            from sqlalchemy import update

            from app.models import WorkflowConfig

            await db.execute(
                update(WorkflowConfig)
                .where(WorkflowConfig.enabled == True)
                .values(last_sync_at=datetime.now(UTC))
            )
            await db.commit()
        except Exception as e:
            logger.error("CI post-sync: update WorkflowConfig.last_sync_at failed: %s", e)

        # 2. 更新本地代码仓库（nightly_config.yaml 快照依赖此缓存）
        try:
            from app.services.github_cache import get_github_cache

            cache = get_github_cache()
            if cache.clone():
                cache.pull()
            logger.info("Local repo updated after CI sync")
        except Exception as e:
            logger.error("CI post-sync: local repo update failed: %s", e)

        # 3. 快照各分支 nightly_config.yaml
        try:
            await self._snapshot_nightly_configs(db)
        except Exception as e:
            logger.error("CI post-sync: snapshot nightly configs failed: %s", e)

        # 4. 物化每日失败记录表
        try:
            count = await self._populate_daily_failure_records(db)
            if count > 0:
                logger.info("Populated %d new daily failure records", count)
        except Exception as e:
            logger.error("CI post-sync: populate daily failure records failed: %s", e)

    async def _sync_ci_data_job(self) -> None:
        """Queue CI synchronization; Collector owns GitHub I/O and all writes."""
        from infrastructure.tasks.task_manager import TaskManager

        params = {
            "days_back": settings.CI_SYNC_DAYS_BACK,
            "max_runs": settings.CI_SYNC_MAX_RUNS_PER_WORKFLOW,
            "force_full_refresh": settings.CI_SYNC_FORCE_FULL_REFRESH,
        }
        dedupe_key = f"ci_sync:scheduled:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "ci_sync",
                params,
                dedupe_key,
                required_capability="python",
            )
            await db.commit()
        if task_id:
            logger.info("Queued CI synchronization task %d", task_id)
        else:
            logger.info("CI synchronization is already queued or running")

    async def _legacy_sync_ci_data_job(self) -> None:
        """CI 数据同步任务"""
        logger.info("=" * 60)
        logger.info("CI DATA SYNC JOB STARTED")
        logger.info("=" * 60)

        if not self.github_client:
            self._initialize_github_client()

        # Phase A Step 3+4: COLLECTOR_MODE 开关
        # true  → Scheduler 只写 pending 任务，Collector 通过租约领取执行
        # false → Scheduler 自己执行（默认，兼容现有流程）
        import os as _os
        _collector_mode = _os.environ.get("COLLECTOR_MODE", "false").lower() == "true"
        from datetime import UTC
        dedupe_key = f"ci_sync:scheduled:{datetime.now(UTC).strftime('%Y-%m-%dT%H:00')}"
        task_id = None
        db_session = SessionLocal()

        try:
            from infrastructure.tasks.task_manager import TaskManager
            async with db_session as db:
                task_id = await TaskManager.create_task(
                    db, "ci_sync",
                    {"days_back": settings.CI_SYNC_DAYS_BACK, "max_runs": settings.CI_SYNC_MAX_RUNS_PER_WORKFLOW},
                    dedupe_key,
                )
                if task_id and not _collector_mode:
                    await TaskManager.start_task(db, task_id, "scheduler")
                await db.commit()
                if task_id and _collector_mode:
                    logger.info("COLLECTOR_MODE: task %d created, waiting for Collector", task_id)
                    return  # Scheduler 不执行，等 Collector 来领
        except Exception as e:
            logger.warning("Failed to create collection_task record (non-fatal): %s", e)

        async with SessionLocal() as db:
            try:
                collector = CICollector(
                    github_client=self.github_client,  # type: ignore
                    db_session=db,
                )

                # 使用配置中的同步策略
                days_back = getattr(settings, 'CI_SYNC_DAYS_BACK', 7)
                max_runs_per_workflow = getattr(settings, 'CI_SYNC_MAX_RUNS_PER_WORKFLOW', 100)
                force_full_refresh = getattr(settings, 'CI_SYNC_FORCE_FULL_REFRESH', False)

                logger.info(f"Sync strategy: days_back={days_back}, max_runs={max_runs_per_workflow}, force_full_refresh={force_full_refresh}")

                collected = await collector.collect_workflow_runs(
                    days_back=days_back,
                    max_runs_per_workflow=max_runs_per_workflow,
                    force_full_refresh=force_full_refresh,
                )

                # 同步完成后，更新所有启用的 workflow 的 last_sync_at
                from sqlalchemy import update

                from infrastructure.persistence.models import WorkflowConfig

                await db.execute(
                    update(WorkflowConfig)
                    .where(WorkflowConfig.enabled == True)
                    .values(last_sync_at=datetime.now(UTC))
                )
                await db.commit()

                # 同步完成后，更新本地代码仓库
                try:
                    from infrastructure.clients.github_cache import get_github_cache
                    cache = get_github_cache()
                    if cache.clone():
                        cache.pull()
                    logger.info("Local repo updated after CI sync")
                except Exception as e:
                    logger.warning(f"Failed to update local repo (non-fatal): {e}")

                # 同步完成后，分析新发现的失败 jobs
                try:
                    await self._analyze_failed_jobs(db)
                except Exception as analyze_err:
                    logger.error(f"Failed to analyze CI failures: {analyze_err}")

                # 数据管线：刷新 last_sync_at / 仓库缓存、快照用例配置、物化每日失败记录。
                # 与 COLLECTOR_MODE collector 共用 run_ci_post_sync，确保两条路径行为一致，
                # 且任一步失败记 ERROR 而非静默吞掉。
                await self.run_ci_post_sync(db)

                logger.info("=" * 60)
                logger.info(f"CI DATA SYNC JOB COMPLETED - Collected {collected} runs")
                logger.info("=" * 60)

                # Step 3: 标记任务完成
                if task_id:
                    try:
                        from infrastructure.tasks.task_manager import TaskManager
                        async with SessionLocal() as td:
                            await TaskManager.complete_task(td, task_id)
                            await td.commit()
                    except Exception as te:
                        logger.warning("Failed to complete collection_task (non-fatal): %s", te)

            except Exception as e:
                logger.error("=" * 60)
                logger.error(f"CI DATA SYNC JOB FAILED - Error: {e}", exc_info=True)
                logger.error("=" * 60)
                # 标记任务失败
                if task_id:
                    try:
                        from infrastructure.tasks.task_manager import TaskManager
                        async with SessionLocal() as td:
                            await TaskManager.fail_task(td, task_id, str(e)[:500])
                            await td.commit()
                    except Exception as te:
                        logger.warning("Failed to fail collection_task (non-fatal): %s", te)
                raise

    async def _sync_pr_pipeline_job(self) -> None:
        """Queue PR synchronization; Collector owns the GitHub I/O and mutation."""
        from infrastructure.tasks.task_manager import TaskManager

        days_back = getattr(settings, "PR_PIPELINE_DAYS_BACK", 7)
        # A stable one-minute window suppresses duplicate enqueues after a
        # Scheduler restart without preventing the next scheduled run.
        dedupe_key = f"pr_sync:scheduled:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "pr_sync",
                {"days_back": days_back},
                dedupe_key,
                required_capability="python",
            )
            await db.commit()

        if task_id:
            logger.info("Queued PR pipeline sync task %d", task_id)
        else:
            logger.info("PR pipeline sync is already queued or running")

    async def _cleanup_logs_job(self) -> None:
        logger.info("LOG CLEANUP JOB STARTED")
        retention_days = getattr(settings, 'DATA_RETENTION_DAYS', 365)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with SessionLocal() as db:
            try:
                from sqlalchemy import delete as sa_delete
                from infrastructure.persistence.models import UserLoginLog, FeatureUsageLog, TokenBlacklist
                lr = await db.execute(sa_delete(UserLoginLog).where(UserLoginLog.login_time < cutoff))
                ur = await db.execute(sa_delete(FeatureUsageLog).where(FeatureUsageLog.access_time < cutoff))
                tr = await db.execute(sa_delete(TokenBlacklist).where(TokenBlacklist.expires_at < datetime.now(UTC)))
                await db.commit()
                logger.info(f"LOG CLEANUP: login={lr.rowcount}, usage={ur.rowcount}, tokens={tr.rowcount}")
            except Exception as e:
                logger.error(f"LOG CLEANUP FAILED: {e}", exc_info=True)
                await db.rollback()

    def _update_project_dashboard_cache_job(self) -> None:
        """Project Dashboard Git 仓库缓存更新任务"""
        logger.info("=" * 60)
        logger.info("PROJECT DASHBOARD CACHE UPDATE JOB STARTED")
        logger.info("=" * 60)

        try:
            from infrastructure.clients.github_cache import get_github_cache, get_github_cache_for_repo
            
            results = []
            
            # 更新 vllm-ascend 仓库
            logger.info("Updating vllm-ascend repository...")
            ascend_cache = get_github_cache()
            if not ascend_cache._is_repo_cloned():
                success = ascend_cache.clone()
                results.append(f"vllm-ascend: {'cloned' if success else 'clone failed'}")
            else:
                success = ascend_cache.pull()
                results.append(f"vllm-ascend: {'pulled' if success else 'pull failed'}")
            
            # 更新 vllm 仓库
            logger.info("Updating vllm repository...")
            vllm_cache = get_github_cache_for_repo(owner="vllm-project", repo="vllm")
            if not vllm_cache._is_repo_cloned():
                success = vllm_cache.clone()
                results.append(f"vllm: {'cloned' if success else 'clone failed'}")
            else:
                success = vllm_cache.pull()
                results.append(f"vllm: {'pulled' if success else 'pull failed'}")
            
            logger.info(f"Cache update results: {', '.join(results)}")
            logger.info("=" * 60)
            logger.info("PROJECT DASHBOARD CACHE UPDATE JOB COMPLETED")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"PROJECT DASHBOARD CACHE UPDATE JOB FAILED - Error: {e}", exc_info=True)
            logger.error("=" * 60)
            raise

    async def _sync_model_reports_job(self) -> None:
        """Queue model report synchronization for a Collector with Python capability."""
        from infrastructure.tasks.task_manager import TaskManager

        params = {
            "days_back": getattr(settings, "MODEL_SYNC_DAYS_BACK", 3),
            "runs_limit": getattr(settings, "MODEL_SYNC_RUNS_LIMIT", 100),
        }
        dedupe_key = f"model_sync:scheduled:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "model_sync",
                params,
                dedupe_key,
                required_capability="python",
            )
            await db.commit()

        if task_id:
            logger.info("Queued model report sync task %d", task_id)
        else:
            logger.info("Model report sync is already queued or running")

    async def _legacy_sync_model_reports_job(self) -> None:
        """模型报告同步任务"""
        logger.info("=" * 60)
        logger.info("MODEL REPORT SYNC JOB STARTED")
        logger.info("=" * 60)

        if not self.github_client:
            self._initialize_github_client()

        async with SessionLocal() as db:
            try:
                from shared.services.model_sync_service import ModelSyncService

                sync_service = ModelSyncService(db, self.github_client)

                # 使用配置中的同步策略
                days_back = getattr(settings, 'MODEL_SYNC_DAYS_BACK', 3)
                runs_limit = getattr(settings, 'MODEL_SYNC_RUNS_LIMIT', 100)

                logger.info(f"Model sync strategy: days_back={days_back}, runs_limit={runs_limit}")

                # 同步所有启用的模型同步配置
                total, collected = await sync_service.sync_all_enabled_configs(
                    days_back=days_back,
                    runs_limit=runs_limit,
                )

                # 同步完成后，更新所有启用的 workflow 的 last_sync_at
                from sqlalchemy import update

                from infrastructure.persistence.models import ModelSyncConfig

                await db.execute(
                    update(ModelSyncConfig)
                    .where(ModelSyncConfig.enabled == True)
                    .values(last_sync_at=datetime.now(UTC))
                )
                await db.commit()

                logger.info("=" * 60)
                logger.info(f"MODEL REPORT SYNC JOB COMPLETED - {total} configs, collected {collected} reports")
                logger.info("=" * 60)

            except Exception as e:
                logger.error("=" * 60)
                logger.error(f"MODEL REPORT SYNC JOB FAILED - Error: {e}", exc_info=True)
                logger.error("=" * 60)
                # async with 会自动 rollback 和 close
                raise

    async def _generate_daily_summary_job(self):
        """每日总结生成任务"""
        logger.info("=" * 60)
        logger.info("DAILY SUMMARY GENERATION JOB STARTED")
        logger.info("=" * 60)
        
        try:
            from datetime import date, timedelta
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker
            from infrastructure.persistence.models.daily_summary import DailySummary
            from infrastructure.persistence.models import ProjectDashboardConfig
            from shared.services.daily_summary import DailySummaryService
            from shared.services.daily_report import _today_shanghai
            from sqlalchemy import select

            # 创建数据库会话
            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as db:
                # 获取配置的项目列表
                projects_stmt = select(ProjectDashboardConfig).where(
                    ProjectDashboardConfig.config_key == 'daily_summary_projects'
                )
                projects_result = await db.execute(projects_stmt)
                projects_config = projects_result.scalar_one_or_none()

                projects = projects_config.config_value if projects_config else [
                    {"id": "ascend", "name": "vLLM Ascend", "enabled": True},
                    {"id": "vllm", "name": "vLLM", "enabled": True},
                ]

                # 计算昨天的日期
                yesterday = _today_shanghai() - timedelta(days=1)

                for project in projects:
                    if not project.get("enabled", True):
                        continue

                    project_id = project.get("id")
                    if not project_id:
                        continue

                    try:
                        # 1. 获取数据
                        logger.info(f"Fetching data for project: {project_id} on {yesterday}")
                        service = DailySummaryService(db)
                        await service.fetch_daily_data(project_id, yesterday)

                        # 2. 生成总结
                        logger.info(f"Generating summary for project: {project_id} on {yesterday}")
                        await service.generate_summary(project_id, yesterday)

                        logger.info(f"Daily summary completed for project: {project_id}")
                    except Exception as e:
                        logger.error(f"Failed to generate summary for {project_id}: {e}", exc_info=True)

                await db.commit()

            logger.info("=" * 60)
            logger.info("DAILY SUMMARY GENERATION JOB COMPLETED")
            logger.info("=" * 60)

        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"DAILY SUMMARY GENERATION JOB FAILED - Error: {e}", exc_info=True)
            logger.error("=" * 60)

    async def _send_daily_report_job(self):
        """每日运行报告邮件推送任务"""
        logger.info("=" * 60)
        logger.info("DAILY REPORT EMAIL JOB STARTED")
        logger.info("=" * 60)

        try:
            from datetime import date, timedelta
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
            from sqlalchemy.orm import sessionmaker
            from sqlalchemy import select
            from infrastructure.persistence.models import ProjectDashboardConfig
            from shared.services.daily_report import DailyReportService, REPORT_CONFIG_KEY, _today_shanghai

            if not settings.REPORT_ENABLED:
                logger.info("Report disabled, skipping")
                return

            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as db:
                # 读报告配置
                stmt = select(ProjectDashboardConfig).where(
                    ProjectDashboardConfig.config_key == REPORT_CONFIG_KEY
                )
                config_result = await db.execute(stmt)
                config = config_result.scalar_one_or_none()
                db_config = config.config_value if config else {}

                # SMTP 配置在单独的 config_key 里
                smtp_stmt = select(ProjectDashboardConfig).where(
                    ProjectDashboardConfig.config_key == "smtp_config"
                )
                smtp_result = await db.execute(smtp_stmt)
                smtp_config = smtp_result.scalar_one_or_none()
                smtp_values = smtp_config.config_value if smtp_config else {}

                if not db_config.get("report_recipients"):
                    logger.info("No recipients configured in DB, skipping")
                    return

                if not smtp_values.get("smtp_host"):
                    logger.info("SMTP_HOST not configured in smtp_config, skipping")
                    return

                yesterday = _today_shanghai() - timedelta(days=1)
                service = DailyReportService(db)
                history = await service.send_report(yesterday)

                logger.info(f"Daily report result: status={history.status}, date={history.report_date}")

            await engine.dispose()

            logger.info("=" * 60)
            logger.info("DAILY REPORT EMAIL JOB COMPLETED")
            logger.info("=" * 60)

        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"DAILY REPORT EMAIL JOB FAILED - Error: {e}", exc_info=True)
            logger.error("=" * 60)
            raise  # Fix #135: re-raise so APScheduler records the failure

    async def _collect_resource_metrics_job(self) -> None:
        """Queue resource metric collection for Collector execution."""
        from infrastructure.tasks.task_manager import TaskManager

        dedupe_key = f"resource_metrics_collect:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "resource_metrics_collect",
                {},
                dedupe_key,
                required_capability="python",
            )
            await db.commit()
        if task_id:
            logger.info("Queued resource metrics collection task %d", task_id)

    async def _analyze_failed_jobs(self, db=None) -> int:
        """
        分析最近失败的、尚未分析的 CI jobs。
        使用 FailureAnalysisService（含 fingerprint 去重）。
        """
        try:
            from sqlalchemy import select

            from infrastructure.persistence.models import CIJob, JobFailureAnalysis
            from shared.services.failure_analysis import FailureAnalysisService

            svc = FailureAnalysisService()
            count = 0

            if db is not None:
                # 查找未分析的失败 jobs
                analyzed_subq = select(JobFailureAnalysis.job_id)
                stmt = (
                    select(CIJob)
                    .where(
                        CIJob.conclusion.in_(["failure", "cancelled"]),
                        CIJob.job_id.notin_(analyzed_subq),
                    )
                    .order_by(CIJob.completed_at.desc().nulls_last())
                    .limit(5)
                )
                result = await db.execute(stmt)
                jobs = result.scalars().all()
                for job in jobs:
                    try:
                        await svc.analyze_failed_job(job.job_id, db, triggered_by="scheduler")
                        count += 1
                    except Exception as e:
                        logger.warning(f"Analysis failed for job {job.job_id}: {e}")
            else:
                async with SessionLocal() as session:
                    analyzed_subq = select(JobFailureAnalysis.job_id)
                    stmt = (
                        select(CIJob)
                        .where(
                            CIJob.conclusion.in_(["failure", "cancelled"]),
                            CIJob.job_id.notin_(analyzed_subq),
                        )
                        .order_by(CIJob.completed_at.desc().nulls_last())
                        .limit(5)
                    )
                    result = await session.execute(stmt)
                    jobs = result.scalars().all()
                    for job in jobs:
                        try:
                            await svc.analyze_failed_job(job.job_id, session)
                            count += 1
                        except Exception as e:
                            logger.warning(f"Analysis failed for job {job.job_id}: {e}")

            return count
        except Exception as e:
            logger.warning(f"Failed job analysis error (non-fatal): {e}")
            return 0

    async def _cleanup_resource_metrics_job(self) -> None:
        """Queue resource metric retention cleanup for Collector execution."""
        from infrastructure.tasks.task_manager import TaskManager

        dedupe_key = f"resource_metrics_cleanup:{datetime.now(UTC).strftime('%Y-%m-%d')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "resource_metrics_cleanup",
                {},
                dedupe_key,
                required_capability="python",
            )
            await db.commit()
        if task_id:
            logger.info("Queued resource metrics cleanup task %d", task_id)

    async def _parse_test_results_job(self) -> None:
        logger.info("TEST BOARD RESULT PARSE JOB STARTED")
        if not self.github_client:
            self._initialize_github_client()
        async with SessionLocal() as db:
            try:
                from shared.services.test_board_service import TestBoardService
                svc = TestBoardService(db, self.github_client)
                count = await svc.parse_ci_results(days_back=7)
                logger.info(f"TEST BOARD RESULT PARSE JOB COMPLETED - {count} results parsed")
                # CI 同步后自动推导发现问题数（auto_issues_found），保持数据最新
                if count > 0:
                    try:
                        from shared.services.issues_found_derivator import IssuesFoundDerivator
                        derivator = IssuesFoundDerivator(db)
                        derivation = await derivator.derive_all()
                        logger.info(
                            "TEST BOARD ISSUES DERIVATION - updated=%d skipped=%d issues=%d suspected=%d",
                            derivation["updated"], derivation["skipped_override"],
                            derivation["issues_total"], derivation["suspected_total"],
                        )
                    except Exception as deriv_err:
                        logger.error(f"TEST BOARD ISSUES DERIVATION FAILED: {deriv_err}", exc_info=True)
            except Exception as e:
                logger.error(f"TEST BOARD RESULT PARSE JOB FAILED: {e}", exc_info=True)

    async def _calc_test_health_job(self) -> None:
        logger.info("TEST BOARD HEALTH CALC JOB STARTED")
        async with SessionLocal() as db:
            try:
                from tooling.analytics.test_health_calculator import TestHealthCalculator
                calc = TestHealthCalculator(db)
                count = await calc.calculate_all_health_scores()
                logger.info(f"TEST BOARD HEALTH CALC JOB COMPLETED - {count} cases updated")
            except Exception as e:
                logger.error(f"TEST BOARD HEALTH CALC JOB FAILED: {e}", exc_info=True)

    async def _snapshot_test_suites_job(self) -> None:
        logger.info("TEST BOARD SUITE SNAPSHOT JOB STARTED")
        async with SessionLocal() as db:
            try:
                from tooling.analytics.test_health_calculator import TestHealthCalculator
                calc = TestHealthCalculator(db)
                count = await calc.calculate_suite_snapshot()
                logger.info(f"TEST BOARD SUITE SNAPSHOT JOB COMPLETED - {count} snapshots")
            except Exception as e:
                logger.error(f"TEST BOARD SUITE SNAPSHOT JOB FAILED: {e}", exc_info=True)

    async def _cleanup_test_runs_job(self) -> None:
        logger.info("TEST BOARD RUN CLEANUP JOB STARTED")
        async with SessionLocal() as db:
            try:
                from tooling.analytics.test_health_calculator import TestHealthCalculator
                calc = TestHealthCalculator(db)
                deleted = await calc.cleanup_old_test_runs()
                logger.info(f"TEST BOARD RUN CLEANUP JOB COMPLETED - {deleted} records deleted")
            except Exception as e:
                logger.error(f"TEST BOARD RUN CLEANUP JOB FAILED: {e}", exc_info=True)

    async def _cleanup_stale_cases_job(self) -> None:
        """物理清理超过 STALE_CASE_DELETE_DAYS 天未运行的已退出测试用例。"""
        logger.info("TEST BOARD STALE CASE CLEANUP JOB STARTED")
        async with SessionLocal() as db:
            try:
                from tooling.analytics.test_health_calculator import TestHealthCalculator
                calc = TestHealthCalculator(db)
                deleted = await calc.cleanup_stale_cases()
                logger.info(f"TEST BOARD STALE CASE CLEANUP JOB COMPLETED - {deleted} stale cases deleted")
            except Exception as e:
                logger.error(f"TEST BOARD STALE CASE CLEANUP JOB FAILED: {e}", exc_info=True)

    def update_daily_summary_schedule(self, enabled: bool, cron_hour: int, cron_minute: int, timezone: str = 'Asia/Shanghai'):
        """
        动态更新每日总结定时任务配置

        Args:
            enabled: 是否启用
            cron_hour: 执行时间（小时）
            cron_minute: 执行时间（分钟）
            timezone: 时区
        """
        from apscheduler.triggers.cron import CronTrigger

        try:
            if enabled:
                self.scheduler.add_job(
                    self._generate_daily_summary_job,
                    trigger=CronTrigger(hour=cron_hour, minute=cron_minute, timezone=timezone),
                    id="daily_summary_task",
                    name="Generate Daily Summary",
                    replace_existing=True,
                )
                logger.info(f"Daily summary schedule updated: {cron_hour}:{cron_minute:02d} {timezone}")
            else:
                try:
                    self.scheduler.remove_job('daily_summary_task')
                except Exception:
                    pass  # 任务可能不存在，忽略错误
                logger.info("Daily summary task disabled")
        except Exception as e:
            logger.error(f"Failed to update daily summary schedule: {e}", exc_info=True)

    def update_resource_metrics_schedule(self, interval_minutes: int = 1):
        """
        动态更新 NPU 指标采集间隔

        Args:
            interval_minutes: 采集间隔（分钟）
        """
        try:
            self.scheduler.add_job(
                self._collect_resource_metrics_job,
                trigger=IntervalTrigger(minutes=interval_minutes),
                id="resource_metrics_collect",
                name="Resource Metrics Collect",
                replace_existing=True,
            )
            logger.info(f"Resource metrics collection schedule updated: every {interval_minutes} minutes")
        except Exception as e:
            logger.error(f"Failed to update resource metrics schedule: {e}", exc_info=True)

    async def trigger_manual_sync(
        self,
        sync_type: str = "ci",
        days_back: int = 7,
        max_runs_per_workflow: int = 100,
        force_full_refresh: bool = False,
    ) -> dict:
        """
        手动触发同步

        Args:
            sync_type: 同步类型 ("ci")
            days_back: 从多少天前开始采集
            max_runs_per_workflow: 每个 workflow 最多采集多少条记录
            force_full_refresh: 是否强制全量覆盖刷新

        Returns:
            同步结果信息
        """
        logger.info(f"Manual sync triggered: {sync_type}, days_back={days_back}, max_runs={max_runs_per_workflow}, force={force_full_refresh}")

        if sync_type != "ci":
            return {
                "success": False,
                "message": f"Unsupported sync type: {sync_type}",
            }

        if not self.github_client:
            self._initialize_github_client()

        async with SessionLocal() as db:
            try:
                collector = CICollector(
                    github_client=self.github_client,  # type: ignore
                    db_session=db,
                )

                collected = await collector.collect_workflow_runs(
                    days_back=days_back,
                    max_runs_per_workflow=max_runs_per_workflow,
                    force_full_refresh=force_full_refresh,
                )

                # 同步完成后，更新进度
                from infrastructure.tasks.sync_progress import get_sync_progress
                progress = get_sync_progress()
                progress.complete()

                # 同步完成后，更新所有启用的 workflow 的 last_sync_at
                from sqlalchemy import update

                from infrastructure.persistence.models import WorkflowConfig

                await db.execute(
                    update(WorkflowConfig)
                    .where(WorkflowConfig.enabled == True)
                    .values(last_sync_at=datetime.now(UTC))
                )
                await db.commit()

                return {
                    "success": True,
                    "message": f"Successfully collected {collected} CI runs",
                    "collected_count": collected,
                }

            except Exception as e:
                logger.error(f"Manual sync failed: {e}", exc_info=True)
                # async with 会自动 rollback 和 close
                raise

    def get_next_run_time(self, job_id: str) -> datetime | None:
        """
        获取任务下次执行时间
        
        Args:
            job_id: 任务 ID
            
        Returns:
            下次执行时间，任务不存在时返回 None
        """
        job = self.scheduler.get_job(job_id)
        if job:
            return job.next_run_time
        return None

    def get_job_info(self) -> list[dict]:
        """
        获取所有任务信息
        
        Returns:
            任务信息列表
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs

    async def _sync_support_matrix_job(self) -> None:
        """每日同步上游支持矩阵"""
        try:
            from infrastructure.db.base import SessionLocal
            from shared.services.support_matrix_sync import sync_support_matrix

            async with SessionLocal() as db:
                result = await sync_support_matrix(db, dry_run=False)
                if result.get("success"):
                    logger.info(
                        f"Support matrix sync: {result.get('models_synced', 0)} models, "
                        f"{len(result.get('new_models', []))} new, "
                        f"{len(result.get('updated_models', []))} updated"
                    )
                else:
                    logger.error(f"Support matrix sync failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Support matrix sync job error: {e}", exc_info=True)

    async def _cleanup_code_metrics_job(self):
        """定时清理过期代码度量明细数据（365天保留）"""
        try:
            from infrastructure.persistence.models import CodeMetricsSnapshot, CodeComplexityDetail, CodeDuplicationDetail, CodeSecurityDetail
            from sqlalchemy import delete, select
            cutoff_date = date.today() - timedelta(days=365)
            async with SessionLocal() as db:
                old_ids = [row[0] for row in (await db.execute(
                    select(CodeMetricsSnapshot.id).where(CodeMetricsSnapshot.snapshot_date < cutoff_date)
                ))]
                if old_ids:
                    await db.execute(delete(CodeComplexityDetail).where(CodeComplexityDetail.snapshot_id.in_(old_ids)))
                    await db.execute(delete(CodeDuplicationDetail).where(CodeDuplicationDetail.snapshot_id.in_(old_ids)))
                    await db.execute(delete(CodeSecurityDetail).where(CodeSecurityDetail.snapshot_id.in_(old_ids)))
                    await db.execute(delete(CodeMetricsSnapshot).where(CodeMetricsSnapshot.id.in_(old_ids)))
                    await db.commit()
                    logger.info(f"Code metrics cleanup: deleted {len(old_ids)} expired snapshots")
        except Exception as e:
            logger.error(f"Code metrics cleanup failed: {e}")

    async def _sync_heatmap_job(self):
        """Queue GitHub heatmap synchronization for Collector execution."""
        from infrastructure.tasks.task_manager import TaskManager

        dedupe_key = f"code_heatmap_sync:scheduled:{datetime.now(UTC).strftime('%Y-%m-%d')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "code_heatmap_sync",
                {"days": 30},
                dedupe_key,
                required_capability="python",
            )
            await db.commit()
        if task_id:
            logger.info("Queued code heatmap synchronization task %d", task_id)

    async def _collect_code_metrics_job(self):
        """Queue code metrics collection; only Collector may run local tools."""
        from infrastructure.tasks.task_manager import TaskManager

        dedupe_key = f"code_metrics:scheduled:{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M')}"
        async with SessionLocal() as db:
            task_id = await TaskManager.create_task(
                db,
                "code_metrics_collect",
                {"branch": "main"},
                dedupe_key,
                required_capability="python",
            )
            await db.commit()
        if task_id:
            logger.info("Queued code metrics collection task %d", task_id)

# 全局调度器实例
_scheduler: DataSyncScheduler | None = None


def get_scheduler() -> DataSyncScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = DataSyncScheduler()
    return _scheduler


def start_scheduler() -> None:
    """启动全局调度器（同步部分：注册默认时间的所有任务）"""
    scheduler = get_scheduler()
    scheduler.start()


async def start_scheduler_async() -> None:
    """启动全局调度器并加载 DB 配置覆盖"""
    scheduler = get_scheduler()
    scheduler.start()
    await scheduler.apply_db_config_overrides()
    await scheduler.write_heartbeat()


async def stop_scheduler_async() -> None:
    """停止全局调度器并清理资源（异步版本）"""
    global _scheduler
    if _scheduler:
        await _scheduler.close()
        _scheduler = None


def stop_scheduler() -> None:
    """停止全局调度器（同步版本，不关闭 GitHub 客户端）"""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        # 注意：同步版本无法关闭异步的 GitHub 客户端
        # 建议使用 stop_scheduler_async
