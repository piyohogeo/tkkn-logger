"""Maintenance and review CLI for the Tokkun '99 logger."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sqlite3
import sys

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.message_collector import MessageCollector  # noqa: E402
from tokkun99_logger.result_reader import ResultReader  # noqa: E402
from tokkun99_logger.storage import ScoreCorrection, Storage  # noqa: E402


def storage() -> Storage:
    value = Storage(DATA_ROOT / "logger.sqlite3", DATA_ROOT)
    value.initialize()
    return value


def command_stats(_: argparse.Namespace) -> int:
    with storage().connect() as connection:
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
            SELECT survival_ms, run_id, ended_at FROM runs
            WHERE status = 'complete' ORDER BY survival_ms DESC LIMIT 1
            """
        ).fetchone()
        bullets = connection.execute(
            """
            SELECT bullet_count, run_id, ended_at FROM runs
            WHERE status = 'complete' ORDER BY bullet_count DESC LIMIT 1
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
    print(
        f"Runs: total={totals['total']}, complete={totals['complete'] or 0}, "
        f"needs_review={totals['needs_review'] or 0}, incomplete={totals['incomplete'] or 0}"
    )
    if survival:
        print(f"Survival record: {survival['survival_ms'] / 1000:.3f}s ({survival['run_id']})")
    if bullets:
        print(f"Bullet record: {bullets['bullet_count']} ({bullets['run_id']})")
    print(
        f"Messages: clusters={messages['clusters']}, labeled={messages['labeled'] or 0}, "
        f"verified={messages['verified'] or 0}, observations={messages['observations']}"
    )
    return 0


def command_review_scores(_: argparse.Namespace) -> int:
    reader = ResultReader(DATA_ROOT / "templates" / "glyphs" / "v1" / "profile.json")
    with storage().connect() as connection:
        rows = connection.execute(
            """
            SELECT run_id, status, survival_ms, bullet_count, score_confidence, result_frame_path
            FROM runs WHERE status IN ('needs_review', 'error') ORDER BY ended_at
            """
        ).fetchall()
    if not rows:
        print("No score reviews are pending.")
        return 0
    for row in rows:
        suggestion = "unavailable"
        if row["result_frame_path"]:
            path = DATA_ROOT / row["result_frame_path"]
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                reading = reader.read(image)
                suggestion = (
                    f"{reading.survival_text}s/{reading.bullet_text}, "
                    f"confidence={reading.confidence:.3f}, review={reading.needs_review}"
                )
        print(
            f"{row['run_id']} status={row['status']} stored={row['survival_ms']}/{row['bullet_count']} "
            f"suggested={suggestion} image={row['result_frame_path']}"
        )
    return 0


def command_correct_score(args: argparse.Namespace) -> int:
    storage().correct_scores(
        [ScoreCorrection(args.run_id, args.survival_ms, args.bullets, args.reason)],
        datetime.now().astimezone().isoformat(),
    )
    print(f"Corrected {args.run_id} to {args.survival_ms} ms / {args.bullets} bullets.")
    return 0


def command_review_messages(_: argparse.Namespace) -> int:
    with storage().connect() as connection:
        rows = connection.execute(
            """
            SELECT c.message_cluster_id, c.observation_count, c.representative_path, c.notes,
                   MIN(r.survival_ms) AS min_survival_ms,
                   MAX(r.survival_ms) AS max_survival_ms
            FROM message_clusters AS c
            LEFT JOIN runs AS r ON r.message_cluster_id = c.message_cluster_id
            WHERE c.merged_into IS NULL AND (c.label_text IS NULL OR c.is_verified = 0)
            GROUP BY c.message_cluster_id
            ORDER BY c.observation_count DESC, c.message_cluster_id
            """
        ).fetchall()
    if not rows:
        print("No message reviews are pending.")
        return 0
    for row in rows:
        survival_range = "unknown"
        if row["min_survival_ms"] is not None:
            survival_range = (
                f"{row['min_survival_ms'] / 1000:.3f}-{row['max_survival_ms'] / 1000:.3f}s"
            )
        print(
            f"cluster={row['message_cluster_id']} observations={row['observation_count']} "
            f"survival_range={survival_range} image={row['representative_path']} "
            f"candidate={row['notes'] or '-'}"
        )
    return 0


def command_label_message(args: argparse.Namespace) -> int:
    MessageCollector(storage()).set_label(args.cluster_id, args.label, verified=args.verified)
    print(f"Labeled message cluster {args.cluster_id}; verified={args.verified}.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stats = commands.add_parser("stats", help="Show records and collection progress")
    stats.set_defaults(handler=command_stats)
    scores = commands.add_parser("review-scores", help="List and re-read pending RESULT images")
    scores.set_defaults(handler=command_review_scores)
    correct = commands.add_parser("correct-score", help="Apply one human-reviewed score correction")
    correct.add_argument("run_id")
    correct.add_argument("survival_ms", type=int)
    correct.add_argument("bullets", type=int)
    correct.add_argument("--reason", required=True)
    correct.set_defaults(handler=command_correct_score)
    messages = commands.add_parser("review-messages", help="List unlabeled or unverified messages")
    messages.set_defaults(handler=command_review_messages)
    label = commands.add_parser("label-message", help="Label one message cluster")
    label.add_argument("cluster_id", type=int)
    label.add_argument("label")
    label.add_argument("--verified", action="store_true")
    label.set_defaults(handler=command_label_message)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
