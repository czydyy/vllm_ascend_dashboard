"""MySQL-backed leadership lease for active Scheduler instances."""
from __future__ import annotations

import os
import socket
import uuid

from sqlalchemy import text

from shared.db.base import SessionLocal


class SchedulerLeaderLease:
    """One active Scheduler per database, with automatic failover after expiry."""

    def __init__(self, *, lease_name: str = "default", ttl_seconds: int = 30) -> None:
        self.lease_name = lease_name
        self.ttl_seconds = ttl_seconds
        self.owner = os.getenv("SCHEDULER_ID", f"scheduler-{socket.gethostname()}")
        self.token = str(uuid.uuid4())

    async def acquire_or_renew(self) -> bool:
        """Acquire an expired lease or renew this instance's existing lease."""
        async with SessionLocal() as db:
            async with db.begin():
                await db.execute(
                    text(
                        """
                        INSERT INTO scheduler_leader_lease
                            (lease_name, lease_owner, lease_token, lease_expiry, generation)
                        VALUES
                            (:name, :owner, :token, NOW() + INTERVAL :ttl SECOND, 1)
                        ON DUPLICATE KEY UPDATE
                            generation = IF(
                                lease_expiry <= NOW() OR lease_token = :token,
                                generation + 1, generation
                            ),
                            lease_owner = IF(
                                lease_expiry <= NOW() OR lease_token = :token,
                                VALUES(lease_owner), lease_owner
                            ),
                            lease_token = IF(
                                lease_expiry <= NOW() OR lease_token = :token,
                                VALUES(lease_token), lease_token
                            ),
                            lease_expiry = IF(
                                lease_expiry <= NOW() OR lease_token = :token,
                                VALUES(lease_expiry), lease_expiry
                            )
                        """
                    ),
                    {
                        "name": self.lease_name,
                        "owner": self.owner,
                        "token": self.token,
                        "ttl": self.ttl_seconds,
                    },
                )
                result = await db.execute(
                    text(
                        """
                        SELECT lease_token FROM scheduler_leader_lease
                        WHERE lease_name = :name FOR UPDATE
                        """
                    ),
                    {"name": self.lease_name},
                )
                return result.scalar_one() == self.token

    async def release(self) -> None:
        """Release only this instance's lease; never disturb a successor."""
        async with SessionLocal() as db:
            async with db.begin():
                await db.execute(
                    text(
                        """
                        UPDATE scheduler_leader_lease
                        SET lease_expiry = NOW()
                        WHERE lease_name = :name AND lease_token = :token
                        """
                    ),
                    {"name": self.lease_name, "token": self.token},
                )
