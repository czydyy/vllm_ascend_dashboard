"""Tests for durable CI sync progress snapshots."""

from infrastructure.tasks.sync_progress import SyncProgress


def test_workflow_progress_does_not_double_count_collected_records() -> None:
    progress = SyncProgress(total_workflows=2)
    progress.start()

    progress.update_collected_count(5)
    progress.update_workflow_progress("workflow-a.yml", 5)

    snapshot = progress.get_progress()
    assert snapshot["completed_workflows"] == 1
    assert snapshot["total_collected"] == 5
    assert snapshot["progress_percentage"] == 50.0
