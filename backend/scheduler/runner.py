"""
Scheduler 独立进程入口。
通过 `python -m app.scheduler` 启动，与 API 进程解耦。
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("app.scheduler")

SHUTDOWN = False


def _handle_shutdown(signum, frame):
    global SHUTDOWN
    logger.info("Received %s, initiating graceful shutdown", signal.Signals(signum).name)
    SHUTDOWN = True


async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_shutdown, sig, None)
        except NotImplementedError:
            signal.signal(sig, _handle_shutdown)

    from app.services.scheduler import get_scheduler, start_scheduler_async, stop_scheduler_async

    await start_scheduler_async()
    scheduler = get_scheduler()
    logger.info("Scheduler started (standalone process)")

    try:
        while not SHUTDOWN:
            await asyncio.sleep(5)
    finally:
        logger.info("Shutting down scheduler...")
        await stop_scheduler_async()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
