from __future__ import annotations

import pytest

from model_sync import litellm_sync


class _Response:
    def __init__(self, status: int, payload: object | None = None, text: str = "") -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def json(self, **_kwargs):
        return self._payload

    async def text(self) -> str:
        return self._text


class _Session:
    def __init__(self, gets: list[_Response]) -> None:
        self.gets = gets

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def get(self, *_args, **_kwargs) -> _Response:
        return self.gets.pop(0)

@pytest.mark.asyncio
async def test_runtime_sync_waits_for_file_watching_proxy(monkeypatch) -> None:
    session = _Session(
        gets=[_Response(200, {"data": []}), _Response(200, {"data": [{"id": "glm-5.2"}]})],
    )
    monkeypatch.setattr(litellm_sync.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(litellm_sync, "_RUNTIME_MODEL_POLL_INTERVAL_SECONDS", 0)
    sync = litellm_sync.LiteLLMSync("http://litellm:4000")

    await sync._wait_for_runtime_models(
        [{"model_name": "glm-5.2", "litellm_params": {"model": "openai/glm-5.2"}}]
    )


@pytest.mark.asyncio
async def test_runtime_sync_fails_when_gateway_does_not_expose_added_model(monkeypatch) -> None:
    session = _Session(
        gets=[_Response(200, {"data": []}), _Response(200, {"data": []})],
    )
    monkeypatch.setattr(litellm_sync.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(litellm_sync, "_RUNTIME_MODEL_POLL_ATTEMPTS", 2)
    monkeypatch.setattr(litellm_sync, "_RUNTIME_MODEL_POLL_INTERVAL_SECONDS", 0)
    sync = litellm_sync.LiteLLMSync("http://litellm:4000")

    with pytest.raises(litellm_sync.LiteLLMConfigSyncError, match="did not load"):
        await sync._wait_for_runtime_models(
            [{"model_name": "glm-5.2", "litellm_params": {"model": "openai/glm-5.2"}}]
        )
