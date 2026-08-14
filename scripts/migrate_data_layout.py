"""Move legacy data into collection/log/template and update database paths."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"


def mapped_relative_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value.replace("\\", "/"))
    parts = path.parts
    if parts[:2] == ("videos", "collection"):
        return PurePosixPath("collection", "videos", *parts[2:]).as_posix()
    if parts[:2] == ("videos", "incomplete"):
        return PurePosixPath("collection", "videos", "incomplete", *parts[2:]).as_posix()
    if parts[:1] == ("runs",):
        return PurePosixPath("collection", "runs", path.name).as_posix()
    if parts[:2] == ("messages", "screens"):
        return PurePosixPath("collection", "messages", *parts[2:]).as_posix()
    if parts[:2] == ("messages", "clusters"):
        return PurePosixPath("log", "messages", *parts[2:]).as_posix()
    return path.as_posix()


def collect_moves(data_root: Path) -> list[tuple[Path, Path]]:
    directory_mappings = (
        ("templates", "template", False),
        ("messages/screens", "collection/messages", False),
        ("messages/clusters", "log/messages", False),
        ("videos/collection", "collection/videos", False),
        ("videos/incomplete", "collection/videos/incomplete", False),
        ("runs", "collection/runs", True),
        ("regression", "log/regression", False),
    )
    moves: list[tuple[Path, Path]] = []
    for old_relative, new_relative, flatten in directory_mappings:
        old_root = data_root / old_relative
        if not old_root.is_dir():
            continue
        for source in old_root.rglob("*"):
            if not source.is_file():
                continue
            relative = Path(source.name) if flatten else source.relative_to(old_root)
            moves.append((source, data_root / new_relative / relative))
    for name in ("logger.sqlite3", "logger.sqlite3-wal", "logger.sqlite3-shm", "logger.lock"):
        source = data_root / name
        if source.is_file():
            moves.append((source, data_root / "log" / name))
    return moves


def update_database_paths(database: Path) -> None:
    if not database.is_file():
        return
    with sqlite3.connect(database) as connection:
        run_rows = connection.execute(
            "SELECT run_id, video_path, result_frame_path FROM runs"
        ).fetchall()
        for run_id, video_path, result_path in run_rows:
            connection.execute(
                "UPDATE runs SET video_path = ?, result_frame_path = ? WHERE run_id = ?",
                (mapped_relative_path(video_path), mapped_relative_path(result_path), run_id),
            )
        cluster_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(message_clusters)")
        }
        if "screen_path" in cluster_columns:
            cluster_rows = connection.execute(
                "SELECT message_cluster_id, representative_path, screen_path FROM message_clusters"
            ).fetchall()
            for cluster_id, representative_path, screen_path in cluster_rows:
                connection.execute(
                    """
                    UPDATE message_clusters SET representative_path = ?, screen_path = ?
                    WHERE message_cluster_id = ?
                    """,
                    (
                        mapped_relative_path(representative_path),
                        mapped_relative_path(screen_path),
                        cluster_id,
                    ),
                )
        else:
            cluster_rows = connection.execute(
                "SELECT message_cluster_id, representative_path FROM message_clusters"
            ).fetchall()
            for cluster_id, representative_path in cluster_rows:
                connection.execute(
                    "UPDATE message_clusters SET representative_path = ? WHERE message_cluster_id = ?",
                    (mapped_relative_path(representative_path), cluster_id),
                )
        variant_rows = connection.execute(
            "SELECT exact_hash, sample_path FROM message_variants"
        ).fetchall()
        for exact_hash, sample_path in variant_rows:
            connection.execute(
                "UPDATE message_variants SET sample_path = ? WHERE exact_hash = ?",
                (mapped_relative_path(sample_path), exact_hash),
            )


def remove_empty_legacy_directories(data_root: Path) -> None:
    for name in ("templates", "messages", "videos", "runs", "regression"):
        root = data_root / name
        if not root.is_dir():
            continue
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.rmdir()
        root.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--apply", action="store_true", help="Perform the migration")
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    moves = collect_moves(data_root)
    destinations: set[Path] = set()
    for source, destination in moves:
        resolved = destination.resolve()
        if data_root not in resolved.parents:
            raise ValueError(f"Destination escaped data root: {destination}")
        if resolved in destinations or destination.exists():
            raise FileExistsError(destination)
        destinations.add(resolved)
    print(f"Planned file moves: {len(moves)}")
    if not args.apply:
        print("Dry run only. Re-run with --apply after stopping the logger and taking a backup.")
        return 0
    for source, destination in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
    update_database_paths(data_root / "log" / "logger.sqlite3")
    remove_empty_legacy_directories(data_root)
    print(f"Data layout migration complete: {data_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
