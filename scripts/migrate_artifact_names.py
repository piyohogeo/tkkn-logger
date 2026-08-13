"""Rename existing run artifacts to sortable score-and-datetime names."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.maintenance import artifact_stem  # noqa: E402
from tokkun99_logger.storage import Storage  # noqa: E402


def relative_target(kind: str, row) -> str:
    stem = artifact_stem(row["survival_ms"], row["started_at"], row["run_id"])
    if kind == "video":
        old_parent = Path(row["video_path"]).parent.as_posix()
        return f"{old_parent}/{stem}.mp4"
    date_path = datetime.fromisoformat(row["started_at"]).strftime("%Y/%m/%d")
    return f"runs/{date_path}/{stem}_result.png"


def checked_path(relative: str) -> Path:
    path = (DATA_ROOT / relative).resolve()
    if DATA_ROOT.resolve() not in path.parents:
        raise ValueError(f"Artifact path escaped data root: {relative}")
    return path


def build_moves(rows) -> list[tuple[str, str, str, str]]:
    moves: list[tuple[str, str, str, str]] = []
    targets: set[Path] = set()
    for row in rows:
        for kind, column in (("video", "video_path"), ("result", "result_frame_path")):
            old_relative = row[column]
            if not old_relative:
                continue
            new_relative = relative_target(kind, row)
            old_path = checked_path(old_relative)
            new_path = checked_path(new_relative)
            if old_path == new_path:
                continue
            if not old_path.is_file():
                raise FileNotFoundError(old_path)
            if new_path.exists() or new_path in targets:
                raise FileExistsError(new_path)
            targets.add(new_path)
            moves.append((row["run_id"], kind, old_relative, new_relative))
    return moves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the rename; default is dry-run")
    args = parser.parse_args()
    storage = Storage(DATA_ROOT / "logger.sqlite3", DATA_ROOT)
    storage.initialize()
    with storage.connect() as connection:
        rows = connection.execute(
            """
            SELECT run_id, started_at, survival_ms, video_path, result_frame_path
            FROM runs ORDER BY started_at, run_id
            """
        ).fetchall()
    moves = build_moves(rows)
    for run_id, kind, old, new in moves:
        print(f"{run_id} {kind}: {old} -> {new}")
    if not args.apply:
        print(f"Dry run: {len(moves)} file(s). Use --apply after review.")
        return 0

    moved: list[tuple[Path, Path]] = []
    connection = storage.connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        changes: dict[str, dict[str, str]] = {}
        for run_id, kind, old_relative, new_relative in moves:
            old_path = checked_path(old_relative)
            new_path = checked_path(new_relative)
            new_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old_path, new_path)
            moved.append((old_path, new_path))
            column = "video_path" if kind == "video" else "result_frame_path"
            connection.execute(
                f"UPDATE runs SET {column} = ? WHERE run_id = ?", (new_relative, run_id)
            )
            changes.setdefault(run_id, {})[kind] = new_relative
        occurred_at = datetime.now().astimezone().isoformat()
        for run_id, paths in changes.items():
            connection.execute(
                "INSERT INTO events(occurred_at, run_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
                (occurred_at, run_id, "artifact_rename", json.dumps(paths, ensure_ascii=False)),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        for old_path, new_path in reversed(moved):
            if new_path.exists() and not old_path.exists():
                old_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(new_path, old_path)
        raise
    finally:
        connection.close()
    print(f"Renamed {len(moves)} file(s) and updated the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
