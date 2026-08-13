from datetime import UTC, datetime, timedelta

import pytest

from infrastructure.clients.github_client import GitHubClient


@pytest.mark.asyncio
async def test_incremental_pr_query_stops_at_updated_watermark():
    client = GitHubClient("test-token")
    since = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
    until = since + timedelta(minutes=30)
    calls: list[int] = []

    async def request(_method, _url, params=None, **_kwargs):
        calls.append(params["page"])
        if params["page"] == 1:
            return [
                {"number": 2, "updated_at": "2026-08-13T10:20:00Z"},
                {"number": 1, "updated_at": "2026-08-13T09:59:59Z"},
            ]
        raise AssertionError("pagination should stop once the watermark is reached")

    client._request = request
    try:
        result = await client.get_pull_requests_by_updated_range(
            "owner", "repo", since, until
        )
    finally:
        await client.close()

    assert [pr["number"] for pr in result] == [2]
    assert calls == [1]


@pytest.mark.asyncio
async def test_incremental_pr_query_honors_max_items():
    client = GitHubClient("test-token")

    async def request(_method, _url, params=None, **_kwargs):
        assert params["sort"] == "updated"
        return [
            {"number": 3, "updated_at": "2026-08-13T10:20:00Z"},
            {"number": 2, "updated_at": "2026-08-13T10:19:00Z"},
            {"number": 1, "updated_at": "2026-08-13T10:18:00Z"},
        ]

    client._request = request
    try:
        result = await client.get_pull_requests_by_updated_range(
            "owner",
            "repo",
            datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 13, 10, 30, tzinfo=UTC),
            max_items=2,
        )
    finally:
        await client.close()

    assert [pr["number"] for pr in result] == [3, 2]
