"""Regression tests for GitHub repository version metadata parsing."""
from __future__ import annotations

from infrastructure.clients.github_cache import GitHubLocalCache


def test_parse_mkdocs_extra_reads_version_keys_and_ignores_nested_values() -> None:
    content = """
extra:
  vllm_version: v0.22.1
  main_python_version: ">= 3.10, < 3.13"
  social:
    - icon: github
  generator: false
nav:
  - index.md
"""

    assert GitHubLocalCache._parse_mkdocs_extra(content) == {
        "vllm_version": "v0.22.1",
        "main_python_version": ">= 3.10, < 3.13",
    }
