from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_model_sync_propagates_github_authentication_failure():
    from infrastructure.clients.github_client import GitHubAuthenticationError
    from model_sync.model_sync_service import ModelSyncService

    class _GitHub:
        async def get_workflow_runs(self, *_args, **_kwargs):
            raise GitHubAuthenticationError("HTTP 401")

    class _Scalars:
        def all(self):
            return [
                SimpleNamespace(
                    workflow_name="model-validation",
                    workflow_file="model-validation.yml",
                    branch="main",
                )
            ]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Database:
        async def execute(self, _statement):
            return _Result()

    service = ModelSyncService(_Database(), _GitHub())

    with pytest.raises(GitHubAuthenticationError):
        await service.sync_all_enabled_configs()
