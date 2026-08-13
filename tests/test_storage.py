from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from tokkun99_logger.storage import RunFinalization, ScoreCorrection, Storage


def make_run(run_id: str, survival: int, bullets: int, video: str | None = "videos/run.mp4") -> RunFinalization:
    return RunFinalization(
        run_id=run_id,
        started_at="2026-08-13T15:00:00+09:00",
        ended_at="2026-08-13T15:00:10+09:00",
        survival_ms=survival,
        bullet_count=bullets,
        score_confidence=1.0,
        status="complete",
        video_path=video,
    )


def initialized_storage(tmp_path: Path) -> Storage:
    data = tmp_path / "data"
    storage = Storage(data / "logger.sqlite3", data)
    storage.initialize()
    (data / "videos").mkdir()
    (data / "videos" / "run.mp4").write_bytes(b"video")
    return storage


def test_two_metrics_update_independently_and_share_video(tmp_path) -> None:
    storage = initialized_storage(tmp_path)

    first = storage.finalize_run(make_run("first", 1000, 50))
    survival_only = storage.finalize_run(make_run("second", 2000, 49))
    bullet_only = storage.finalize_run(make_run("third", 1500, 60))
    neither = storage.finalize_run(make_run("fourth", 1500, 60))

    assert (first.is_survival_record, first.is_bullet_record) == (True, True)
    assert (survival_only.is_survival_record, survival_only.is_bullet_record) == (True, False)
    assert (bullet_only.is_survival_record, bullet_only.is_bullet_record) == (False, True)
    assert (neither.is_survival_record, neither.is_bullet_record) == (False, False)
    with storage.connect() as connection:
        paths = connection.execute(
            "SELECT DISTINCT video_path FROM runs WHERE is_survival_record OR is_bullet_record"
        ).fetchall()
        history = connection.execute(
            "SELECT metric, value FROM records_history ORDER BY record_id"
        ).fetchall()
    assert [row["video_path"] for row in paths] == ["videos/run.mp4"]
    assert [(row["metric"], row["value"]) for row in history] == [
        ("survival_ms", 1000),
        ("bullet_count", 50),
        ("survival_ms", 2000),
        ("bullet_count", 60),
    ]


def test_record_without_finalized_video_rolls_back(tmp_path) -> None:
    storage = initialized_storage(tmp_path)

    with pytest.raises(ValueError, match="finalized video"):
        storage.finalize_run(make_run("missing", 1000, 50, "videos/missing.mp4"))

    with storage.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_review_run_never_updates_records(tmp_path) -> None:
    storage = initialized_storage(tmp_path)
    run = make_run("review", 9999, 999)
    review = RunFinalization(**{**run.__dict__, "status": "needs_review", "video_path": None})

    result = storage.finalize_run(review)

    assert (result.is_survival_record, result.is_bullet_record) == (False, False)


def test_rejects_absolute_or_parent_paths(tmp_path) -> None:
    storage = initialized_storage(tmp_path)

    with pytest.raises(ValueError, match="relative"):
        storage.finalize_run(make_run("bad", 1000, 50, "../outside.mp4"))


def test_reviewed_correction_rebuilds_record_history(tmp_path) -> None:
    storage = initialized_storage(tmp_path)
    storage.finalize_run(make_run("first", 1000, 50))
    storage.finalize_run(make_run("wrong", 900, 999))

    storage.correct_scores(
        [ScoreCorrection("wrong", 900, 49, "Result layout correction")],
        "2026-08-13T16:00:00+09:00",
    )

    with storage.connect() as connection:
        wrong = connection.execute(
            "SELECT bullet_count, is_bullet_record FROM runs WHERE run_id = 'wrong'"
        ).fetchone()
        valid = connection.execute(
            "SELECT metric, value, run_id FROM records_history WHERE is_valid = 1 ORDER BY record_id"
        ).fetchall()
        invalid = connection.execute(
            "SELECT value FROM records_history WHERE is_valid = 0 AND value = 999"
        ).fetchone()
        event = connection.execute(
            "SELECT event_type FROM events WHERE run_id = 'wrong'"
        ).fetchone()
    assert (wrong["bullet_count"], wrong["is_bullet_record"]) == (49, 0)
    assert [(row["metric"], row["value"], row["run_id"]) for row in valid] == [
        ("survival_ms", 1000, "first"),
        ("bullet_count", 50, "first"),
    ]
    assert invalid["value"] == 999
    assert event["event_type"] == "score_correction"


def test_detach_nonrecord_video_but_protect_record_video(tmp_path) -> None:
    storage = initialized_storage(tmp_path)
    storage.finalize_run(make_run("record", 1000, 50))
    ordinary_video = storage.data_root / "videos" / "ordinary.mp4"
    ordinary_video.write_bytes(b"video")
    storage.finalize_run(make_run("ordinary", 900, 49, "videos/ordinary.mp4"))

    detached = storage.detach_nonrecord_video("ordinary", "2026-08-13T16:00:00+09:00")

    assert detached == "videos/ordinary.mp4"
    with storage.connect() as connection:
        row = connection.execute(
            "SELECT video_path FROM runs WHERE run_id = 'ordinary'"
        ).fetchone()
        event = connection.execute(
            "SELECT event_type FROM events WHERE run_id = 'ordinary'"
        ).fetchone()
    assert row["video_path"] is None
    assert event["event_type"] == "video_detached"
    with pytest.raises(ValueError, match="Record videos"):
        storage.detach_nonrecord_video("record", "2026-08-13T16:00:00+09:00")
