"""回归测试：FormatProxy 对推理模型的禁思考参数注入。

glm-5.3 等推理模型先输出长思考再产出 content，思考阶段上游返回
空流/空 content，claude CLI 表现为 "Stream ended without receiving
any events" 并无限重试（分析任务租约超时循环）。
默认注入 reasoning_effort=none；FORMAT_PROXY_DISABLE_THINKING=false 可关闭。
"""
from tooling.parsers.format_proxy import FormatProxy


def _make() -> FormatProxy:
    return FormatProxy(
        upstream_base_url="https://example.com/v1",
        upstream_api_key="k",
        upstream_model="glm-5.3",
    )


def test_default_injects_reasoning_effort_none(monkeypatch):
    monkeypatch.delenv("FORMAT_PROXY_DISABLE_THINKING", raising=False)
    proxy = _make()

    body = proxy._anthropic_to_openai({"model": "claude", "max_tokens": 100, "messages": []})

    assert body["reasoning_effort"] == "none"


def test_env_kill_switch_disables_injection(monkeypatch):
    monkeypatch.setenv("FORMAT_PROXY_DISABLE_THINKING", "false")
    proxy = _make()

    body = proxy._anthropic_to_openai({"model": "claude", "max_tokens": 100, "messages": []})

    assert "reasoning_effort" not in body
