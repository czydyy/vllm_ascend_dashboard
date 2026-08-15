from __future__ import annotations

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_github_config_rejects_credentials_rejected_by_github(monkeypatch):
    from api.v1 import system_config
    from infrastructure.clients import github_client

    class _RejectedClient:
        def __init__(self, _token):
            pass

        async def get_rate_limit_status(self):
            raise github_client.GitHubAuthenticationError("HTTP 401")

        async def close(self):
            pass

    monkeypatch.setattr(github_client, "GitHubClient", _RejectedClient)

    with pytest.raises(HTTPException) as exc_info:
        await system_config.update_github_config(
            payload=system_config.GitHubConfigUpdateRequest(
                github_token="ghp_invalid_for_test"
            ),
            current_user=None,
        )

    assert exc_info.value.status_code == 400
    assert "失效" in str(exc_info.value.detail)
