"""Business services with lazy exports.

Keeping package import side-effect free lets workers and tests load one service without
requiring every optional integration (scheduler, Kubernetes, and so on).
"""

from importlib import import_module

_EXPORTS = {
    "CICollector": ("app.services.ci_collector", "CICollector"),
    "GitHubAPIError": ("app.services.github_client", "GitHubAPIError"),
    "GitHubClient": ("app.services.github_client", "GitHubClient"),
    "GitHubRateLimitError": ("app.services.github_client", "GitHubRateLimitError"),
    "ModelReportParser": ("app.services.model_report_parser", "ModelReportParser"),
    "ModelSyncService": ("app.services.model_sync_service", "ModelSyncService"),
    "ModelTrendService": ("app.services.model_trend_service", "ModelTrendService"),
    "StartupCommandGenerator": (
        "app.services.startup_command_generator",
        "StartupCommandGenerator",
    ),
    "DataSyncScheduler": ("shared.scheduler_service", "DataSyncScheduler"),
    "get_scheduler": ("shared.scheduler_service", "get_scheduler"),
    "start_scheduler": ("shared.scheduler_service", "start_scheduler"),
    "start_scheduler_async": ("shared.scheduler_service", "start_scheduler_async"),
    "stop_scheduler": ("shared.scheduler_service", "stop_scheduler"),
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
