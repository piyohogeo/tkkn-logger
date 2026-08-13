"""Replay collected frames through the debounced state detector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.state_detector import DebouncedStateDetector, StateClassifier  # noqa: E402


DEFAULT_PROFILE = PROJECT_ROOT / "data" / "templates" / "states" / "v1" / "profile.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = args.session.resolve()
    classifier = StateClassifier(args.profile)
    detector = DebouncedStateDetector(classifier, stable_frames=3)
    transitions: list[dict[str, object]] = []
    last_image = None
    with (session / "frames.jsonl").open(encoding="utf-8") as events:
        for line in events:
            event = json.loads(line)
            if event["saved_path"]:
                last_image = cv2.imread(str(session / event["saved_path"]), cv2.IMREAD_COLOR)
            if last_image is None:
                raise RuntimeError("First event did not contain an image")
            observation = detector.observe(last_image)
            if observation.changed:
                transitions.append(
                    {
                        "index": event["index"],
                        "elapsed_seconds": event["elapsed_seconds"],
                        "state": observation.state.value,
                        "title_score": observation.scores.title,
                        "result_score": observation.scores.result,
                    }
                )
    output = session / "state_replay.json"
    output.write_text(json.dumps({"transitions": transitions}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(transitions, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
