"""Collect MESSAGE transition frames from a calibration session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.message_collector import MessageCollector  # noqa: E402
from tokkun99_logger.state_detector import DebouncedStateDetector, GameState, StateClassifier  # noqa: E402
from tokkun99_logger.storage import Storage  # noqa: E402


DEFAULT_STATE_PROFILE = PROJECT_ROOT / "data" / "template" / "states" / "v1" / "profile.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--state-profile", type=Path, default=DEFAULT_STATE_PROFILE)
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data" / "log" / "logger.sqlite3")
    args = parser.parse_args()
    session = args.session.resolve()
    storage = Storage(args.database, PROJECT_ROOT / "data")
    storage.initialize()
    collector = MessageCollector(storage)
    detector = DebouncedStateDetector(StateClassifier(args.state_profile), stable_frames=3)
    assignments = []
    last_image = None
    with (session / "frames.jsonl").open(encoding="utf-8") as events:
        for line in events:
            event = json.loads(line)
            if event["saved_path"]:
                last_image = cv2.imread(str(session / event["saved_path"]), cv2.IMREAD_COLOR)
            observation = detector.observe(last_image)
            if observation.changed and observation.state == GameState.MESSAGE:
                assignment = collector.collect(last_image, event["captured_at"])
                assignments.append({"index": event["index"], **assignment.__dict__})
    output = session / "message_replay.json"
    output.write_text(json.dumps({"assignments": assignments}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(assignments, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
