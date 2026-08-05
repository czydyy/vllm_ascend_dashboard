"""
Collector 独立进程入口。
通过 `python -m app.collector` 启动。

读取 NODE_ID 和 CAPABILITIES 环境变量，使用 CollectorWorker 基类
对接现有 CICollector、PerformanceCollector 等具体采集逻辑。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("app.collector")


async def main():
    node_id = os.environ.get("NODE_ID", f"collector-{os.uname().nodename}")
    capabilities_str = os.environ.get("CAPABILITIES", "python")
    capabilities = [c.strip() for c in capabilities_str.split(",") if c.strip()]

    from app.db.base import SessionLocal
    from app.services.collector_base import CollectorWorker
    from app.services.collector_runner import CollectorRunner

    worker = CollectorWorker(
        node_id=node_id,
        capabilities=capabilities,
        db_session_factory=SessionLocal,
    )

    # 委托给 CollectorRunner 执行具体采集逻辑
    runner = CollectorRunner(worker)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
