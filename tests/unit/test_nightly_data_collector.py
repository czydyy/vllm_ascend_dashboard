from types import SimpleNamespace

from collector.nightly_data import NightlyDataCollector


def _snapshot(*, report_date: str, branch: str = "main", workflow: str = "Nightly-A3", job_name: str, test_model: str):
    return SimpleNamespace(
        report_date=report_date,
        source_branch=branch,
        workflow_name=workflow,
        job_name=job_name,
        test_model=test_model,
    )


def test_match_snapshot_prefers_exact_report_date():
    old = _snapshot(
        report_date="2026-08-13",
        job_name="old-model",
        test_model="old-model.yaml",
    )
    exact = _snapshot(
        report_date="2026-08-14",
        job_name="new-model",
        test_model="new-model.yaml",
    )
    snapshot_map = {
        ("2026-08-13", "main", "Nightly-A3", old.job_name): old,
        ("2026-08-14", "main", "Nightly-A3", exact.job_name): exact,
    }

    result = NightlyDataCollector._match_snapshot(
        snapshot_map,
        {("main", "Nightly-A3"): [exact, old]},
        report_date="2026-08-14",
        source_branch="main",
        workflow_name="Nightly-A3",
        job_name="single-node (main, new-model.yaml) / new-model",
    )

    assert result is exact


def test_match_snapshot_falls_back_for_historical_job_without_exact_snapshot():
    current = _snapshot(
        report_date="2026-08-14",
        job_name="MiniMax-M3-W8A8-A3",
        test_model="MiniMax-M3-W8A8-A3.yaml",
    )

    result = NightlyDataCollector._match_snapshot(
        {
            ("2026-08-14", "main", "Nightly-A3", current.job_name): current,
        },
        {("main", "Nightly-A3"): [current]},
        report_date="2026-08-12",
        source_branch="main",
        workflow_name="Nightly-A3",
        job_name="single-node (main, MiniMax-M3-W8A8-A3.yaml) / MiniMax-M3-W8A8-A3",
    )

    assert result is current
