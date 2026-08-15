"""Read-only dashboard statistics shared by GUI and CLI."""

from __future__ import annotations

from dataclasses import dataclass

from .storage import Storage


@dataclass(frozen=True)
class RecordValue:
    value: int
    run_id: str


@dataclass(frozen=True)
class DashboardStats:
    total_runs: int = 0
    complete_runs: int = 0
    needs_review_runs: int = 0
    incomplete_runs: int = 0
    survival_record: RecordValue | None = None
    bullet_record: RecordValue | None = None
    message_clusters: int = 0
    labeled_messages: int = 0
    verified_messages: int = 0
    message_observations: int = 0


def load_dashboard(storage: Storage) -> DashboardStats:
    storage.initialize()
    with storage.connect() as connection:
        totals = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(status = 'complete') AS complete,
                   SUM(status = 'needs_review') AS needs_review,
                   SUM(status = 'incomplete') AS incomplete
            FROM runs
            """
        ).fetchone()
        survival = connection.execute(
            """
            SELECT survival_ms, run_id FROM runs
            WHERE status = 'complete' AND survival_ms IS NOT NULL
            ORDER BY survival_ms DESC LIMIT 1
            """
        ).fetchone()
        bullets = connection.execute(
            """
            SELECT bullet_count, run_id FROM runs
            WHERE status = 'complete' AND bullet_count IS NOT NULL
            ORDER BY bullet_count DESC LIMIT 1
            """
        ).fetchone()
        messages = connection.execute(
            """
            SELECT COUNT(*) AS clusters,
                   SUM(label_text IS NOT NULL) AS labeled,
                   SUM(is_verified = 1) AS verified,
                   COALESCE(SUM(observation_count), 0) AS observations
            FROM message_clusters WHERE merged_into IS NULL
            """
        ).fetchone()
    return DashboardStats(
        total_runs=int(totals["total"] or 0),
        complete_runs=int(totals["complete"] or 0),
        needs_review_runs=int(totals["needs_review"] or 0),
        incomplete_runs=int(totals["incomplete"] or 0),
        survival_record=(
            RecordValue(int(survival["survival_ms"]), str(survival["run_id"]))
            if survival is not None
            else None
        ),
        bullet_record=(
            RecordValue(int(bullets["bullet_count"]), str(bullets["run_id"]))
            if bullets is not None
            else None
        ),
        message_clusters=int(messages["clusters"] or 0),
        labeled_messages=int(messages["labeled"] or 0),
        verified_messages=int(messages["verified"] or 0),
        message_observations=int(messages["observations"] or 0),
    )
