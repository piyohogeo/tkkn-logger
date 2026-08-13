"""SQLite persistence and atomic two-metric record updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import json
import sqlite3
from typing import Literal


SCHEMA_VERSION = 2
Metric = Literal["survival_ms", "bullet_count"]


@dataclass(frozen=True)
class RunFinalization:
    run_id: str
    started_at: str
    ended_at: str
    survival_ms: int | None
    bullet_count: int | None
    score_confidence: float
    status: str
    video_path: str | None = None
    result_frame_path: str | None = None
    message_cluster_id: int | None = None
    capture_profile_id: str | None = None
    recognizer_version: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class FinalizationResult:
    run_id: str
    is_survival_record: bool
    is_bullet_record: bool


@dataclass(frozen=True)
class ScoreCorrection:
    run_id: str
    survival_ms: int
    bullet_count: int
    reason: str
    status: str = "complete"


def _relative_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Path must be relative to data root: {value}")
    return path.as_posix()


class Storage:
    def __init__(self, database_path: Path, data_root: Path) -> None:
        self.database_path = database_path.resolve()
        self.data_root = data_root.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    schema_version INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_clusters (
                    message_cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    perceptual_hash TEXT,
                    representative_path TEXT NOT NULL,
                    label_text TEXT,
                    notes TEXT,
                    is_verified INTEGER NOT NULL DEFAULT 0 CHECK (is_verified IN (0, 1)),
                    merged_into INTEGER REFERENCES message_clusters(message_cluster_id),
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS message_variants (
                    exact_hash TEXT PRIMARY KEY,
                    message_cluster_id INTEGER NOT NULL REFERENCES message_clusters(message_cluster_id),
                    sample_path TEXT NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    survival_ms INTEGER,
                    bullet_count INTEGER,
                    score_confidence REAL NOT NULL CHECK (score_confidence >= 0 AND score_confidence <= 1),
                    status TEXT NOT NULL CHECK (status IN ('complete', 'needs_review', 'incomplete', 'error')),
                    is_survival_record INTEGER NOT NULL DEFAULT 0 CHECK (is_survival_record IN (0, 1)),
                    is_bullet_record INTEGER NOT NULL DEFAULT 0 CHECK (is_bullet_record IN (0, 1)),
                    message_cluster_id INTEGER REFERENCES message_clusters(message_cluster_id),
                    video_path TEXT,
                    result_frame_path TEXT,
                    capture_profile_id TEXT,
                    recognizer_version TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS records_history (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric TEXT NOT NULL CHECK (metric IN ('survival_ms', 'bullet_count')),
                    value INTEGER NOT NULL,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    achieved_at TEXT NOT NULL,
                    is_valid INTEGER NOT NULL DEFAULT 1 CHECK (is_valid IN (0, 1)),
                    invalidated_at TEXT,
                    invalidation_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    run_id TEXT REFERENCES runs(run_id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_records_metric_value
                    ON records_history(metric, value DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_survival ON runs(survival_ms DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_bullets ON runs(bullet_count DESC);
                """
            )
            row = connection.execute("SELECT schema_version FROM schema_info LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_info(schema_version) VALUES (?)", (SCHEMA_VERSION,))
            elif row["schema_version"] == 1:
                columns = {
                    column["name"]
                    for column in connection.execute("PRAGMA table_info(records_history)").fetchall()
                }
                if "is_valid" not in columns:
                    connection.execute(
                        "ALTER TABLE records_history ADD COLUMN is_valid INTEGER NOT NULL DEFAULT 1"
                    )
                    connection.execute("ALTER TABLE records_history ADD COLUMN invalidated_at TEXT")
                    connection.execute("ALTER TABLE records_history ADD COLUMN invalidation_reason TEXT")
                connection.execute("UPDATE schema_info SET schema_version = ?", (SCHEMA_VERSION,))
            elif row["schema_version"] != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported schema version {row['schema_version']}; expected {SCHEMA_VERSION}"
                )

    @staticmethod
    def _current_record(connection: sqlite3.Connection, metric: Metric) -> int | None:
        row = connection.execute(
            "SELECT MAX(value) AS value FROM records_history WHERE metric = ? AND is_valid = 1", (metric,)
        ).fetchone()
        return row["value"] if row and row["value"] is not None else None

    def _video_exists(self, relative_path: str | None) -> bool:
        return relative_path is not None and (self.data_root / relative_path).is_file()

    def finalize_run(self, run: RunFinalization) -> FinalizationResult:
        video_path = _relative_path(run.video_path)
        result_frame_path = _relative_path(run.result_frame_path)
        if run.survival_ms is not None and run.survival_ms < 0:
            raise ValueError("survival_ms must be non-negative")
        if run.bullet_count is not None and run.bullet_count < 0:
            raise ValueError("bullet_count must be non-negative")
        if not 0 <= run.score_confidence <= 1:
            raise ValueError("score_confidence must be between 0 and 1")

        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_survival = self._current_record(connection, "survival_ms")
            current_bullets = self._current_record(connection, "bullet_count")
            eligible = run.status == "complete" and run.survival_ms is not None and run.bullet_count is not None
            survival_record = bool(
                eligible and (current_survival is None or run.survival_ms > current_survival)
            )
            bullet_record = bool(
                eligible and (current_bullets is None or run.bullet_count > current_bullets)
            )
            if (survival_record or bullet_record) and not self._video_exists(video_path):
                raise ValueError("A confirmed record requires an existing finalized video")

            connection.execute(
                """
                INSERT INTO runs (
                    run_id, started_at, ended_at, survival_ms, bullet_count,
                    score_confidence, status, is_survival_record, is_bullet_record,
                    message_cluster_id, video_path, result_frame_path,
                    capture_profile_id, recognizer_version, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.started_at,
                    run.ended_at,
                    run.survival_ms,
                    run.bullet_count,
                    run.score_confidence,
                    run.status,
                    int(survival_record),
                    int(bullet_record),
                    run.message_cluster_id,
                    video_path,
                    result_frame_path,
                    run.capture_profile_id,
                    run.recognizer_version,
                    run.notes,
                ),
            )
            for metric, value, is_record in (
                ("survival_ms", run.survival_ms, survival_record),
                ("bullet_count", run.bullet_count, bullet_record),
            ):
                if is_record and value is not None:
                    connection.execute(
                        "INSERT INTO records_history(metric, value, run_id, achieved_at) VALUES (?, ?, ?, ?)",
                        (metric, value, run.run_id, run.ended_at),
                    )
            connection.commit()
            return FinalizationResult(run.run_id, survival_record, bullet_record)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def correct_scores(self, corrections: list[ScoreCorrection], corrected_at: str) -> None:
        """Apply reviewed corrections and rebuild valid record history atomically."""
        if not corrections:
            return
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for correction in corrections:
                if correction.survival_ms < 0 or correction.bullet_count < 0:
                    raise ValueError("Corrected scores must be non-negative")
                row = connection.execute(
                    "SELECT survival_ms, bullet_count, status FROM runs WHERE run_id = ?",
                    (correction.run_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"Unknown run: {correction.run_id}")
                old_values = {
                    "survival_ms": row["survival_ms"],
                    "bullet_count": row["bullet_count"],
                    "status": row["status"],
                }
                connection.execute(
                    """
                    UPDATE runs
                    SET survival_ms = ?, bullet_count = ?, status = ?,
                        score_confidence = 1.0
                    WHERE run_id = ?
                    """,
                    (
                        correction.survival_ms,
                        correction.bullet_count,
                        correction.status,
                        correction.run_id,
                    ),
                )
                connection.execute(
                    "INSERT INTO events(occurred_at, run_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
                    (
                        corrected_at,
                        correction.run_id,
                        "score_correction",
                        json.dumps(
                            {
                                "old": old_values,
                                "new": {
                                    "survival_ms": correction.survival_ms,
                                    "bullet_count": correction.bullet_count,
                                    "status": correction.status,
                                },
                                "reason": correction.reason,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )

            reason = "record history rebuilt after reviewed score correction"
            connection.execute(
                """
                UPDATE records_history
                SET is_valid = 0, invalidated_at = ?, invalidation_reason = ?
                WHERE is_valid = 1
                """,
                (corrected_at, reason),
            )
            connection.execute(
                "UPDATE runs SET is_survival_record = 0, is_bullet_record = 0"
            )
            best_survival: int | None = None
            best_bullets: int | None = None
            runs = connection.execute(
                """
                SELECT run_id, ended_at, survival_ms, bullet_count
                FROM runs
                WHERE status = 'complete' AND survival_ms IS NOT NULL AND bullet_count IS NOT NULL
                ORDER BY ended_at, run_id
                """
            ).fetchall()
            for row in runs:
                survival_record = best_survival is None or row["survival_ms"] > best_survival
                bullet_record = best_bullets is None or row["bullet_count"] > best_bullets
                connection.execute(
                    "UPDATE runs SET is_survival_record = ?, is_bullet_record = ? WHERE run_id = ?",
                    (int(survival_record), int(bullet_record), row["run_id"]),
                )
                for metric, value, is_record in (
                    ("survival_ms", row["survival_ms"], survival_record),
                    ("bullet_count", row["bullet_count"], bullet_record),
                ):
                    if is_record:
                        connection.execute(
                            """
                            INSERT INTO records_history(metric, value, run_id, achieved_at, is_valid)
                            VALUES (?, ?, ?, ?, 1)
                            """,
                            (metric, value, row["run_id"], row["ended_at"]),
                        )
                if survival_record:
                    best_survival = int(row["survival_ms"])
                if bullet_record:
                    best_bullets = int(row["bullet_count"])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def detach_nonrecord_video(self, run_id: str, occurred_at: str) -> str | None:
        """Atomically remove a non-record video's DB reference before file deletion."""
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT video_path, is_survival_record, is_bullet_record
                FROM runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown run: {run_id}")
            if row["is_survival_record"] or row["is_bullet_record"]:
                raise ValueError("Record videos must not be detached")
            video_path = row["video_path"]
            if video_path is None:
                connection.commit()
                return None
            connection.execute("UPDATE runs SET video_path = NULL WHERE run_id = ?", (run_id,))
            remaining_references = connection.execute(
                "SELECT COUNT(*) FROM runs WHERE video_path = ?", (video_path,)
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO events(occurred_at, run_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
                (
                    occurred_at,
                    run_id,
                    "video_detached",
                    json.dumps(
                        {
                            "video_path": video_path,
                            "file_deletion_allowed": remaining_references == 0,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            connection.commit()
            return str(video_path) if remaining_references == 0 else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
