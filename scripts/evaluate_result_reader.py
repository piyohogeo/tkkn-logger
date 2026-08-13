"""Evaluate RESULT recognition against reviewed values in the local database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.result_reader import ResultReader  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maximum-shift",
        type=int,
        help="Override the profile's maximum glyph translation for this evaluation",
    )
    parser.add_argument("--details", action="store_true", help="Print every mismatch")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = ResultReader(DATA_ROOT / "templates" / "glyphs" / "v1" / "profile.json")
    if args.maximum_shift is not None:
        if args.maximum_shift < 0:
            raise SystemExit("maximum-shift must be non-negative")
        reader.maximum_shift = args.maximum_shift
    connection = sqlite3.connect(DATA_ROOT / "logger.sqlite3")
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT run_id, survival_ms, bullet_count, result_frame_path
        FROM runs
        WHERE status = 'complete' AND result_frame_path IS NOT NULL
        ORDER BY started_at, run_id
        """
    ).fetchall()
    exact = review = wrong_accept = 0
    mismatches = []
    for row in rows:
        image = cv2.imread(str(DATA_ROOT / row["result_frame_path"]), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(row["result_frame_path"])
        reading = reader.read(image)
        expected = (row["survival_ms"], row["bullet_count"])
        actual = (reading.survival_ms, reading.bullet_count)
        is_exact = actual == expected
        exact += int(is_exact)
        review += int(reading.needs_review)
        wrong_accept += int(not reading.needs_review and not is_exact)
        if not is_exact:
            mismatches.append(
                (row["run_id"], *expected, *actual, reading.needs_review, reading.confidence)
            )
    print(
        f"total={len(rows)} exact={exact} review={review} "
        f"wrong_accept={wrong_accept} not_exact={len(mismatches)}"
    )
    if args.details:
        for mismatch in mismatches:
            print(mismatch)
    return 1 if wrong_accept else 0


if __name__ == "__main__":
    raise SystemExit(main())
