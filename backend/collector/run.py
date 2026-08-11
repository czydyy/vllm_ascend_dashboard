"""Collector service entrypoint.

The collector is the only role that leases and executes durable collection
tasks; it is deployed independently from API and scheduler processes.
"""

import asyncio

from app.collector import main


if __name__ == "__main__":
    asyncio.run(main())
