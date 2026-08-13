from __future__ import annotations

from pathlib import Path

import pytest

from tokkun99_logger.maintenance import (
    InstanceLock,
    discard_detached_video,
    ensure_disk_capacity,
    recover_partial_videos,
)
from tokkun99_logger.storage import RunFinalization, Storage


def test_recover_partial_videos_moves_to_quarantine(tmp_path: Path) -> None:
    data = tmp_path / "data"
    partial = data / "videos" / "collection" / "run.partial.mp4"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")

    result = recover_partial_videos(data)

    assert not partial.exists()
    assert len(result.recovered) == 1
    assert result.recovered[0].read_bytes() == b"partial"
    assert result.recovered[0].parent == data / "videos" / "incomplete" / "recovered"
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
    video = data / "videos" / "ordinary.mp4"
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
            video_path="videos/ordinary.mp4",
        )
    )

    assert discard_detached_video(storage, "ordinary", "2026-08-13T16:00:00+09:00")
    assert not video.exists()
