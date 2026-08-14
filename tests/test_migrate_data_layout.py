from __future__ import annotations

from pathlib import Path
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from migrate_data_layout import mapped_relative_path, update_database_paths  # noqa: E402


def test_maps_legacy_data_paths() -> None:
    assert mapped_relative_path("videos/collection/run.mp4") == "collection/videos/run.mp4"
    assert mapped_relative_path("videos/incomplete/run.mp4") == (
        "collection/videos/incomplete/run.mp4"
    )
    assert mapped_relative_path("runs/2026/08/14/run.png") == "collection/runs/run.png"
    assert mapped_relative_path("messages/screens/message.png") == (
        "collection/messages/message.png"
    )
    assert mapped_relative_path("messages/clusters/hash.png") == "log/messages/hash.png"
    assert mapped_relative_path(None) is None


def test_updates_database_artifact_references(tmp_path: Path) -> None:
    database = tmp_path / "logger.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                video_path TEXT,
                result_frame_path TEXT
            );
            INSERT INTO runs VALUES (
                'run-1', 'videos/collection/run.mp4', 'runs/2026/08/14/result.png'
            );
            CREATE TABLE message_clusters (
                message_cluster_id INTEGER PRIMARY KEY,
                representative_path TEXT,
                screen_path TEXT
            );
            INSERT INTO message_clusters VALUES (
                1, 'messages/clusters/hash.png', 'messages/screens/message.png'
            );
            CREATE TABLE message_variants (exact_hash TEXT PRIMARY KEY, sample_path TEXT);
            INSERT INTO message_variants VALUES ('hash', 'messages/clusters/hash.png');
            """
        )

    update_database_paths(database)

    with sqlite3.connect(database) as connection:
        run = connection.execute("SELECT video_path, result_frame_path FROM runs").fetchone()
        cluster = connection.execute(
            "SELECT representative_path, screen_path FROM message_clusters"
        ).fetchone()
        variant = connection.execute("SELECT sample_path FROM message_variants").fetchone()
    assert run == ("collection/videos/run.mp4", "collection/runs/result.png")
    assert cluster == ("log/messages/hash.png", "collection/messages/message.png")
    assert variant == ("log/messages/hash.png",)
