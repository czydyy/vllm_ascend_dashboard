"""Business services with lazy exports.

Keeping package import side-effect free lets workers and tests load one service without
requiring every optional integration (scheduler, Kubernetes, and so on).
"""

from importlib import import_module

_EXPORTS = {
    "GitHubAPIError": ("infrastructure.clients.github_client", "GitHubAPIError"),
    "GitHubClient": ("infrastructure.clients.github_client", "GitHubClient"),
    "GitHubRateLimitError": ("infrastructure.clients.github_client", "GitHubRateLimitError"),
    "ModelReportParser": ("shared.services.model_report_parser", "ModelReportParser"),
    "ModelSyncService": ("shared.services.model_sync_service", "ModelSyncService"),
    "ModelTrendService": ("shared.services.model_trend_service", "ModelTrendService"),
    "StartupCommandGenerator": (
        "shared.services.startup_command_generator",
        "StartupCommandGenerator",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
