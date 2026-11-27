"""Parse GitHub Actions workflow_dispatch inputs."""

import re
from typing import NotRequired, TypedDict

import yaml  # type: ignore[import-untyped]

_BOOLEAN_TAG = "tag:yaml.org,2002:bool"
_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


WorkflowInputValue = str | bool | int | float | None


class WorkflowInput(TypedDict):
    name: str
    type: str
    description: str
    required: bool
    options: list[str]
    default: NotRequired[WorkflowInputValue]


class _WorkflowLoader(yaml.SafeLoader):
    # Workflow files use "on" as a key and may include bare strings such as "off".
    yaml_implicit_resolvers = {
        key: [entry for entry in entries if entry[0] not in {_BOOLEAN_TAG, _TIMESTAMP_TAG}]
        for key, entries in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }


_WorkflowLoader.add_implicit_resolver(
    _BOOLEAN_TAG, re.compile(r"^(true|false)$", re.IGNORECASE), list("tTfF")
)


def parse_dispatch_inputs(source: str) -> list[WorkflowInput] | None:
    """Return inputs in declaration order, or None if the workflow has no dispatch event."""
    try:
        document = yaml.load(source, Loader=_WorkflowLoader)
    except yaml.YAMLError as exc:
        raise ValueError("无效的 Workflow YAML") from exc
    if not isinstance(document, dict):
        raise ValueError("Workflow YAML 必须是映射")

    events = document.get("on")
    if events == "workflow_dispatch" or (
        isinstance(events, list) and "workflow_dispatch" in events
    ):
        return []
    if not isinstance(events, dict) or "workflow_dispatch" not in events:
        return None

    dispatch = events["workflow_dispatch"]
    if dispatch is None:
        return []
    if not isinstance(dispatch, dict):
        raise ValueError("无效的 workflow_dispatch 定义")
    definitions = dispatch.get("inputs")
    if definitions is None:
        return []
    if not isinstance(definitions, dict):
        raise ValueError("无效的 workflow_dispatch.inputs 定义")

    inputs: list[WorkflowInput] = []
    for name, definition in definitions.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            raise ValueError("无效的 Workflow 参数")
        input_type = definition.get("type", "string")
        description = definition.get("description", "")
        required = definition.get("required", False)
        options = definition.get("options", [])
        if (
            not isinstance(input_type, str)
            or not isinstance(description, str)
            or not isinstance(required, bool)
            or not isinstance(options, list)
            or not all(isinstance(option, str) for option in options)
        ):
            raise ValueError(f"无效的 Workflow 参数定义: {name}")

        field: WorkflowInput = {
            "name": name,
            "type": input_type,
            "description": description,
            "required": required,
            "options": options,
        }
        if "default" in definition:
            value = definition["default"]
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise ValueError(f"无效的 Workflow 参数默认值: {name}")
            field["default"] = value
        inputs.append(field)
    return inputs
