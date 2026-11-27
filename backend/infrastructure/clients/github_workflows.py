"""Read dispatch definitions and environment options from GitHub."""

import base64

import httpx

from tooling.parsers.workflow_dispatch import WorkflowInput, parse_dispatch_inputs

_PAGE_SIZE = 100
_MAX_PAGES = 100


async def list_workflow_environments(client: httpx.AsyncClient, repository: str) -> list[str]:
    names: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        response = await client.get(
            f"/repos/{repository}/environments",
            params={"per_page": _PAGE_SIZE, "page": page},
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("environments") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError("无效的 GitHub 环境列表")
        for item in items:
            name = item.get("name") if isinstance(item, dict) else None
            if not isinstance(name, str) or not name:
                raise ValueError("GitHub 环境记录缺少名称")
            names.add(name)
        if "next" not in response.links:
            return sorted(names)
    raise ValueError("GitHub 环境列表未完成分页")


async def read_workflow_inputs(
    client: httpx.AsyncClient, repository: str, path: str, ref: str,
) -> list[WorkflowInput] | None:
    response = await client.get(
        f"/repos/{repository}/contents/{path}", params={"ref": ref}
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64":
        raise ValueError("GitHub 返回了无效的 Workflow 文件")
    content = data.get("content")
    if not isinstance(content, str):
        raise ValueError("GitHub Workflow 文件缺少内容")
    source = base64.b64decode("".join(content.split()), validate=True).decode("utf-8")
    return parse_dispatch_inputs(source)
