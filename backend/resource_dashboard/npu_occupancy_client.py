"""Read-only client for pod-history-api.  Persistence belongs to Step 3."""
from __future__ import annotations

import gzip
import json
import ssl
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from infrastructure.core.config import settings


class NpuOccupancyUpstreamError(RuntimeError):
    pass


class NpuOccupancyClient:
    chunk = timedelta(hours=12)
    minimum_chunk = timedelta(minutes=45)
    attempts = 3

    def __init__(self, *, url: str | None = None, timeout_seconds: int | None = None, verify_tls: bool | None = None):
        self.url = url or settings.NPU_OCCUPANCY_UPSTREAM_URL
        self.timeout_seconds = timeout_seconds or settings.NPU_OCCUPANCY_TIMEOUT_SECONDS
        self.verify_tls = settings.NPU_OCCUPANCY_VERIFY_TLS if verify_tls is None else verify_tls

    @staticmethod
    def _utc(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _context(self) -> ssl.SSLContext:
        return ssl.create_default_context() if self.verify_tls else ssl._create_unverified_context()

    def _fetch(self, start: datetime, end: datetime, *, active_only: bool = False) -> list[dict]:
        query = {"start_time": self._utc(start), "end_time": self._utc(end)}
        if active_only:
            query["status"] = "active"
        request = Request(f"{self.url}?{urlencode(query)}", headers={"Accept-Encoding": "gzip", "User-Agent": "vllm-ascend-dashboard/npu-occupancy"})
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self._context()) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # urllib exposes several transport exception types
            raise NpuOccupancyUpstreamError(f"pod-history-api request failed: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("envs"), list):
            raise NpuOccupancyUpstreamError("pod-history-api payload does not contain an envs list")
        return [item for item in payload["envs"] if isinstance(item, dict)]

    def _fetch_resilient(self, start: datetime, end: datetime, *, active_only: bool = False, depth: int = 0) -> list[dict]:
        error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return self._fetch(start, end, active_only=active_only)
            except NpuOccupancyUpstreamError as exc:
                error = exc
                if attempt < self.attempts - 1:
                    time.sleep(0.25 * (attempt + 1))
        if end - start <= self.minimum_chunk or depth >= 4:
            raise NpuOccupancyUpstreamError(f"pod-history-api failed for {self._utc(start)} to {self._utc(end)}: {error}")
        middle = start + (end - start) / 2
        return self._fetch_resilient(start, middle, active_only=active_only, depth=depth + 1) + self._fetch_resilient(middle, end, active_only=active_only, depth=depth + 1)

    def fetch_window(self, start: datetime, end: datetime) -> list[dict]:
        records: list[dict] = []
        cursor = start
        while cursor < end:
            next_cursor = min(cursor + self.chunk, end)
            records.extend(self._fetch_resilient(cursor, next_cursor))
            cursor = next_cursor
        return records
