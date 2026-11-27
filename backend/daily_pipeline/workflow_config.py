"""Sync and validate the dispatch parameters of the configured Daily workflow."""

import json
import logging
from math import isfinite

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.clients.daily_pipeline_config import DAILY_WORKFLOW
from infrastructure.clients.github_http import GitHubAsyncClient
from infrastructure.clients.github_workflows import list_workflow_environments, read_workflow_inputs
from infrastructure.core.github_credentials import daily_github_credential
from infrastructure.db.mysql_lock import mysql_named_lock
from infrastructure.persistence.daily_pipeline_settings import read_settings, set_setting
from tooling.parsers.workflow_dispatch import WorkflowInput, WorkflowInputValue

DEFINITION_KEY = "dispatch_workflow_definition"
VALUES_KEY = "dispatch_workflow_inputs"
WORKFLOW_PATH = f".github/workflows/{DAILY_WORKFLOW}"
MAX_CONFIG_BYTES = 65_535
SOURCE_BRANCH_INPUT = "vllm_ascend_branch"
CASE_SELECTION_INPUTS = frozenset({"daily_test_cases", "daily_config_yaml"})
MANAGED_INPUTS = CASE_SELECTION_INPUTS | {SOURCE_BRANCH_INPUT}
logger = logging.getLogger(__name__)


class WorkflowSyncBusy(ValueError):
    """The configured workflow is already being synchronized."""


def _scoped_config(settings: dict[str, str | None], key: str) -> dict | None:
    try:
        value = json.loads(settings.get(key) or "null")
    except ValueError:
        return None
    if isinstance(value, dict) and (
        value.get("repository"), value.get("branch")
    ) == (settings.get("repository"), settings.get("source_branch")):
        return value
    return None


def _config_fields(fields: list[WorkflowInput]) -> list[WorkflowInput]:
    return [field for field in fields if field["name"] not in CASE_SELECTION_INPUTS]


def _editable_fields(definition: dict) -> list[WorkflowInput]:
    return [field for field in definition["inputs"] if field["name"] not in MANAGED_INPUTS]


def _validate_value(field: WorkflowInput, value: WorkflowInputValue) -> None:
    kind = field["type"]
    if kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "number":
        valid = type(value) is int or isinstance(value, float) and isfinite(value)
    elif kind in ("choice", "environment"):
        valid = isinstance(value, str) and value in field["options"]
    else:
        valid = isinstance(value, str)
    if not valid:
        raise ValueError(f"Workflow 参数 {field['name']} 的值无效")


def workflow_config(settings: dict[str, str | None]) -> dict | None:
    definition = _scoped_config(settings, DEFINITION_KEY)
    if definition is None:
        return None
    saved = (_scoped_config(settings, VALUES_KEY) or {}).get("inputs", {})
    inputs = _editable_fields(definition)
    return {
        "repository": definition["repository"],
        "branch": definition["branch"],
        "path": WORKFLOW_PATH,
        "inputs": inputs,
        "values": {
            field["name"]: saved.get(field["name"], field.get("default"))
            for field in inputs
        },
    }


async def sync_daily_workflow(db: AsyncSession) -> None:
    async with mysql_named_lock("daily-workflow-definition") as acquired:
        if not acquired:
            raise WorkflowSyncBusy("Daily Workflow 正在同步")
        source = await read_settings(db, "repository", "source_branch", "github_token")
        repository, branch = source.get("repository"), source.get("source_branch")
        if not repository or not branch:
            raise ValueError("请先配置 Daily 仓库和来源分支")
        credential = daily_github_credential(source)
        credential.validate()
        await db.rollback()

        async with GitHubAsyncClient(audit_source="daily_config", credential=credential, timeout=15) as client:
            fields = await read_workflow_inputs(client, repository, WORKFLOW_PATH, branch)
            if fields is None:
                raise ValueError("配置分支缺少可手动触发的 Daily Workflow")
            test_cases = next((field for field in fields if field["name"] == "daily_test_cases"), None)
            if test_cases is None or test_cases["type"] != "string":
                raise ValueError("Daily Workflow 必须声明字符串类型的 daily_test_cases 参数")
            fields = _config_fields(fields)
            environments = [field for field in fields if field["type"] == "environment"]
            if environments:
                options = await list_workflow_environments(client, repository)
                for field in environments:
                    field["options"] = options

        latest = await read_settings(db, "repository", "source_branch")
        if (repository, branch) != (latest.get("repository"), latest.get("source_branch")):
            raise ValueError("Daily 仓库或来源分支已变更，请重新同步")
        definition = {"repository": repository, "branch": branch, "inputs": fields}
        encoded = json.dumps(definition, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_CONFIG_BYTES:
            raise ValueError("Workflow 参数定义内容过长")
        await set_setting(db, DEFINITION_KEY, encoded)
        await db.commit()
        logger.info("Daily Workflow synced repository=%s branch=%s inputs=%s", repository, branch, len(fields))


async def save_workflow_values(db: AsyncSession, values: dict[str, WorkflowInputValue]) -> None:
    settings = await read_settings(db, "repository", "source_branch", DEFINITION_KEY)
    definition = _scoped_config(settings, DEFINITION_KEY)
    if definition is None:
        raise ValueError("请先同步 Daily Workflow")
    fields = {field["name"]: field for field in _editable_fields(definition)}
    if values.keys() - fields.keys():
        raise ValueError("Workflow 参数定义已变更，请刷新配置")
    overrides = {}
    for name, value in values.items():
        if value is None:
            continue
        field = fields[name]
        if value != "" or field["type"] == "string":
            _validate_value(field, value)
            if value != field.get("default") or type(value) is not type(field.get("default")):
                overrides[name] = value
    data = {"repository": definition["repository"], "branch": definition["branch"], "inputs": overrides}
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("Workflow 参数内容过长")
    await set_setting(db, VALUES_KEY, encoded)


def daily_dispatch_inputs(
    settings: dict[str, str | None], branch: str, cases: dict[str, list[str]],
) -> dict[str, WorkflowInputValue]:
    definition = _scoped_config(settings, DEFINITION_KEY)
    inputs: dict[str, WorkflowInputValue] = {"daily_test_cases": json.dumps(cases, ensure_ascii=False)}
    if definition is None:
        return {**inputs, SOURCE_BRANCH_INPUT: branch}

    fields = {field["name"]: field for field in definition["inputs"]}
    if SOURCE_BRANCH_INPUT in fields:
        _validate_value(fields[SOURCE_BRANCH_INPUT], branch)
        inputs[SOURCE_BRANCH_INPUT] = branch
    saved = (_scoped_config(settings, VALUES_KEY) or {}).get("inputs", {})
    for field in _editable_fields(definition):
        name = field["name"]
        value = saved.get(name, field.get("default"))
        if value is None or value == "":
            if field["required"]:
                raise ValueError(f"请配置 Workflow 参数 {name}")
            if value == "" and field["type"] == "string":
                inputs[name] = value
            continue
        _validate_value(field, value)
        inputs[name] = value
    return inputs
