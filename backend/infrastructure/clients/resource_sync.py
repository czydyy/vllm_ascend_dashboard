"""Pull resource dashboards from a remote collector endpoint.

The production collector remains the only component that talks to Kubernetes.
Local development collectors can pull the already-authorized dashboard result
over HTTP and persist it in their own database.  This keeps the local runtime
independent from private Kubernetes networks while retaining the normal
durable resource-metrics task.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from contracts.schemas import ResourceDashboardResponse
from infrastructure.core.config import settings

logger = logging.getLogger(__name__)


class RemoteResourceDashboardClient:
    """Authenticate and fetch the production resource dashboard."""

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(
            settings.RESOURCE_METRICS_REMOTE_URL
            and settings.RESOURCE_METRICS_REMOTE_USERNAME
            and settings.RESOURCE_METRICS_REMOTE_PASSWORD
        )

    async def fetch_dashboard(self) -> ResourceDashboardResponse:
        if not self.enabled:
            raise RuntimeError("remote resource metrics source is not configured")

        timeout = httpx.Timeout(float(settings.RESOURCE_METRICS_REMOTE_TIMEOUT_SECONDS), connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            token = await self._ensure_access_token(client)
            response = await client.get(
                self._endpoint("resource-dashboard/summary"),
                params={"include_pods": "true"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code == httpx.codes.UNAUTHORIZED:
                await self._reset_token()
                token = await self._ensure_access_token(client)
                response = await client.get(
                    self._endpoint("resource-dashboard/summary"),
                    params={"include_pods": "true"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            response.raise_for_status()
            return ResourceDashboardResponse.model_validate(response.json())

    async def _ensure_access_token(self, client: httpx.AsyncClient) -> str:
        if self._access_token:
            return self._access_token
        async with self._lock:
            if self._access_token:
                return self._access_token
            response = await client.post(
                self._endpoint("auth/login"),
                json={
                    "username": settings.RESOURCE_METRICS_REMOTE_USERNAME,
                    "password": settings.RESOURCE_METRICS_REMOTE_PASSWORD,
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            token = payload.get("access_token")
            if not token:
                raise RuntimeError("remote resource metrics login returned no access token")
            self._access_token = str(token)
            self._refresh_token = payload.get("refresh_token")
            return self._access_token

    async def _reset_token(self) -> None:
        async with self._lock:
            self._access_token = None
            self._refresh_token = None

    def _endpoint(self, path: str) -> str:
        return f"{settings.RESOURCE_METRICS_REMOTE_URL.rstrip('/')}/{path.lstrip('/')}"


_client: RemoteResourceDashboardClient | None = None


def get_remote_resource_dashboard_client() -> RemoteResourceDashboardClient:
    global _client
    if _client is None:
        _client = RemoteResourceDashboardClient()
    return _client
