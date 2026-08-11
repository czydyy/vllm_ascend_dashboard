"""Scheduler service entrypoint.

The scheduling process is deployed separately from the HTTP API. Shared domain
and persistence code remain importable from the application package.
"""

import asyncio

from app.scheduler import main


if __name__ == "__main__":
    asyncio.run(main())
