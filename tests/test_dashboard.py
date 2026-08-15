from __future__ import annotations

from tokkun99_logger.dashboard import load_dashboard
from tokkun99_logger.storage import RunFinalization, Storage


def test_dashboard_handles_empty_and_populated_database(tmp_path) -> None:
    storage = Storage(tmp_path / "data" / "log" / "logger.sqlite3", tmp_path / "data")
    empty = load_dashboard(storage)
    assert empty.total_runs == 0
    assert empty.survival_record is None
    assert empty.bullet_record is None

    video = tmp_path / "data" / "collection" / "videos" / "run.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    storage.finalize_run(
        RunFinalization(
            run_id="run-1",
            started_at="2026-08-15T10:00:00+09:00",
            ended_at="2026-08-15T10:00:10+09:00",
            survival_ms=8000,
            bullet_count=52,
            score_confidence=1.0,
            status="complete",
            video_path="collection/videos/run.mp4",
        )
    )

    populated = load_dashboard(storage)
    assert (populated.total_runs, populated.complete_runs) == (1, 1)
    assert populated.survival_record and populated.survival_record.value == 8000
    assert populated.bullet_record and populated.bullet_record.value == 52
