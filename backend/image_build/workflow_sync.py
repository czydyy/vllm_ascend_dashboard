"""Discover Nightly image build parameters from their GitHub workflow definitions."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from sqlalchemy import select

from image_build.config import get_image_build_repository
from infrastructure.clients.github_http import GitHubAsyncClient
from infrastructure.clients.github_workflows import list_workflow_environments, read_workflow_inputs
from infrastructure.db.base import SessionLocal
from infrastructure.db.mysql_lock import mysql_named_lock
from infrastructure.persistence.models import ImageBuildWorkflowDefinition
from tooling.parsers.workflow_dispatch import WorkflowInput
from tooling.parsers.workflow_dispatch import parse_dispatch_inputs as parse_dispatch_inputs
from workflow_actions.credentials import get_github_credential

WORKFLOW_PATH = ".github/workflows/schedule_nightly_image_build_with_base.yaml"

_PAGE_SIZE = 100
_MAX_PAGES = 100
logger = logging.getLogger(__name__)


class WorkflowSyncInProgress(RuntimeError):
    pass


class WorkflowSyncCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowSyncResult:
    branches: int
    changed: int
    failed: int


@asynccontextmanager
async def _workflow_sync_lock() -> AsyncIterator[None]:
    async with mysql_named_lock("image-build-workflow-sync") as acquired:
        if not acquired:
            raise WorkflowSyncInProgress
        yield


async def _list_branches(client: httpx.AsyncClient, repository: str) -> dict[str, str]:
    branches: dict[str, str] = {}
    for page in range(1, _MAX_PAGES + 1):
        response = await client.get(
            f"/repos/{repository}/branches",
            params={"per_page": _PAGE_SIZE, "page": page},
        )
        response.raise_for_status()
        items = response.json()
        if not isinstance(items, list):
            raise ValueError("无效的 GitHub 分支列表")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("commit"), dict):
                raise ValueError("无效的 GitHub 分支记录")
            name, sha = item.get("name"), item["commit"].get("sha")
            if not isinstance(name, str) or not name or not isinstance(sha, str) or not sha:
                raise ValueError("GitHub 分支记录缺少分支名或提交 SHA")
            if name in branches and branches[name] != sha:
                raise ValueError("GitHub 分支列表在分页期间发生变化")
            branches[name] = sha
        if "next" not in response.links:
            if not branches:
                raise ValueError("GitHub 返回了空的仓库分支列表")
            return branches
    raise ValueError("GitHub 分支列表未完成分页")


async def _save_definition(repository: str, branch_name: str, inputs: list[WorkflowInput] | None) -> bool:
    inputs_hash = None
    if inputs is not None:
        encoded = json.dumps(
            inputs, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
        ).encode("utf-8")
        inputs_hash = hashlib.sha256(encoded).hexdigest()

    async with SessionLocal.begin() as db:
        definition = await db.get(
            ImageBuildWorkflowDefinition, (repository, branch_name), with_for_update=True,
        )
        if inputs is None:
            if definition is None or not definition.is_available:
                return False
            definition.is_available = False
        elif definition is None:
            db.add(
                ImageBuildWorkflowDefinition(
                    repository=repository,
                    branch_name=branch_name,
                    inputs_json=inputs,
                    inputs_hash=inputs_hash,
                    is_available=True,
                )
            )
        elif definition.inputs_hash != inputs_hash or not definition.is_available:
            definition.inputs_json = inputs
            definition.inputs_hash = inputs_hash
            definition.is_available = True
        else:
            return False
        return True


class ImageBuildWorkflowSync:
    def __init__(self) -> None:
        # A missing file is only cached for the exact commit and for this Scheduler process.
        self._unsupported_heads: dict[str, str] = {}
        self._cached_repository: str | None = None

    async def run(self) -> WorkflowSyncResult:
        async with _workflow_sync_lock():
            async with SessionLocal() as db:
                repository = await get_image_build_repository(db)
                try:
                    credential = await get_github_credential(db)
                except ValueError as exc:
                    raise WorkflowSyncCredentialError(str(exc)) from exc

            async with GitHubAsyncClient(
                audit_source="image_build_workflow_sync",
                credential=credential,
                timeout=httpx.Timeout(15, connect=5),
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            ) as client:
                return await self.sync(client, repository)

    async def sync(self, client: httpx.AsyncClient, repository: str) -> WorkflowSyncResult:
        # Finish pagination before using an absent branch to deactivate a definition.
        branches = await _list_branches(client, repository)
        if self._cached_repository != repository:
            self._unsupported_heads.clear()
            self._cached_repository = repository
        self._unsupported_heads = {
            branch: sha
            for branch, sha in self._unsupported_heads.items()
            if branches.get(branch) == sha
        }
        async with SessionLocal() as db:
            rows = await db.execute(
                select(
                    ImageBuildWorkflowDefinition.branch_name,
                    ImageBuildWorkflowDefinition.is_available,
                ).where(ImageBuildWorkflowDefinition.repository == repository)
            )
            known = dict(rows.all())

        changed = 0
        failed = 0
        environment_options: list[str] | None = None
        checked_environments = False
        for branch in sorted(branches, key=lambda name: name in known):
            sha = branches[branch]
            if self._unsupported_heads.get(branch) == sha:
                continue
            try:
                inputs = await read_workflow_inputs(client, repository, WORKFLOW_PATH, sha)
                environment_inputs = [field for field in (inputs or []) if field["type"] == "environment"]
                if environment_inputs:
                    # Environment names belong to the repository and are shared by all branches.
                    if not checked_environments:
                        checked_environments = True
                        try:
                            environment_options = await list_workflow_environments(client, repository)
                        except (httpx.HTTPError, ValueError) as exc:
                            logger.warning("Could not sync image build workflow environments: %s", exc)
                    if environment_options is None:
                        failed += 1
                        continue
                    for field in environment_inputs:
                        field["options"] = environment_options
                if inputs is not None or known.get(branch):
                    changed += await _save_definition(repository, branch, inputs)
                if inputs is None:
                    self._unsupported_heads[branch] = sha
            except (httpx.HTTPError, ValueError) as exc:
                failed += 1
                logger.warning("Could not sync image build workflow on %s: %s", branch, exc)
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {
                    401,
                    403,
                    429,
                }:
                    break

        for branch in known.keys() - branches.keys():
            if known[branch]:
                changed += await _save_definition(repository, branch, None)

        logger.info(
            "Image build workflow sync: repository=%s branches=%d changed=%d failed=%d",
            repository,
            len(branches),
            changed,
            failed,
        )
        return WorkflowSyncResult(branches=len(branches), changed=changed, failed=failed)
