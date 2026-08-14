from __future__ import annotations

from pathlib import Path

import pytest

from tokkun99_logger.maintenance import (
    InstanceLock,
    artifact_stem,
    discard_detached_video,
    ensure_disk_capacity,
    recover_partial_videos,
)
from tokkun99_logger.storage import RunFinalization, Storage


def test_artifact_stem_sorts_by_survival_and_contains_datetime() -> None:
    earlier_score = artifact_stem(
        5520, "2026-08-13T15:42:21.789455+09:00", "a872f26d-edce-4ed5-87c2-be2476523d15"
    )
    later_score = artifact_stem(
        40624, "2026-08-13T15:40:35.732226+09:00", "c7caa9b2-1924-47a1-88d3-7f75f4d5392a"
    )

    assert earlier_score == (
        "000000005520ms_2026-08-13_15-42-21+0900_a872f26d-edce-4ed5-87c2-be2476523d15"
    )
    assert earlier_score < later_score
    assert artifact_stem(None, "2026-08-13T15:42:21+09:00", "run-1").startswith(
        "unknown_2026-08-13_15-42-21+0900_"
    )


@pytest.mark.parametrize("filename", ["run.mp4.incomplete", "legacy.partial.mp4"])
def test_recover_partial_videos_moves_to_quarantine(tmp_path: Path, filename: str) -> None:
    data = tmp_path / "data"
    partial = data / "collection" / "videos" / filename
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")

    result = recover_partial_videos(data)

    assert not partial.exists()
    assert len(result.recovered) == 1
    assert result.recovered[0].read_bytes() == b"partial"
    assert result.recovered[0].parent == data / "collection" / "videos" / "incomplete" / "recovered"
    assert result.recovered[0].name.endswith(".mp4.incomplete")
    assert recover_partial_videos(data).recovered == ()


def test_instance_lock_rejects_second_owner(tmp_path: Path) -> None:
    first = InstanceLock(tmp_path / "logger.lock")
    second = InstanceLock(tmp_path / "logger.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            second.acquire()
    finally:
        first.release()


def test_disk_capacity_guard_rejects_impossible_requirement(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="Insufficient free disk space"):
        ensure_disk_capacity(tmp_path, minimum_free_bytes=10**30)


def test_discard_detached_video_removes_only_nonrecord(tmp_path: Path) -> None:
    data = tmp_path / "data"
    video = data / "collection" / "videos" / "ordinary.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    storage = Storage(data / "logger.sqlite3", data)
    storage.initialize()
    storage.finalize_run(
        RunFinalization(
            run_id="ordinary",
            started_at="2026-08-13T15:00:00+09:00",
            ended_at="2026-08-13T15:00:01+09:00",
            survival_ms=1,
            bullet_count=1,
            score_confidence=1.0,
            status="needs_review",
            video_path="collection/videos/ordinary.mp4",
        )
    )

    assert discard_detached_video(storage, "ordinary", "2026-08-13T16:00:00+09:00")
    assert not video.exists()
