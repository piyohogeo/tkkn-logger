"""Replay a calibration session into run boundaries and consensus scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.result_reader import ResultConsensus, ResultReader  # noqa: E402
from tokkun99_logger.state_detector import DebouncedStateDetector, GameState, StateClassifier  # noqa: E402


DEFAULT_STATE_PROFILE = PROJECT_ROOT / "data" / "templates" / "states" / "v1" / "profile.json"
DEFAULT_GLYPH_PROFILE = PROJECT_ROOT / "data" / "templates" / "glyphs" / "v1" / "profile.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--state-profile", type=Path, default=DEFAULT_STATE_PROFILE)
    parser.add_argument("--glyph-profile", type=Path, default=DEFAULT_GLYPH_PROFILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = args.session.resolve()
    detector = DebouncedStateDetector(StateClassifier(args.state_profile), stable_frames=3)
    reader = ResultReader(args.glyph_profile)
    runs: list[dict[str, object]] = []
    current_run: dict[str, object] | None = None
    consensus: ResultConsensus | None = None
    last_image = None

    with (session / "frames.jsonl").open(encoding="utf-8") as events:
        for line in events:
            event = json.loads(line)
            if event["saved_path"]:
                last_image = cv2.imread(str(session / event["saved_path"]), cv2.IMREAD_COLOR)
            if last_image is None:
                raise RuntimeError("First event did not contain an image")
            observation = detector.observe(last_image)

            if observation.changed and observation.state == GameState.PLAYING:
                if current_run is not None:
                    current_run["status"] = "incomplete"
                    runs.append(current_run)
                current_run = {
                    "started_index": event["index"],
                    "started_elapsed_seconds": event["elapsed_seconds"],
                    "status": "playing",
                }
                consensus = None
            elif observation.changed and observation.state == GameState.RESULT and current_run is not None:
                current_run["result_index"] = event["index"]
                consensus = ResultConsensus(required_frames=5)
            elif observation.changed and observation.state == GameState.MESSAGE and current_run is not None:
                resolved = consensus.resolve() if consensus is not None else None
                current_run["message_index"] = event["index"]
                if resolved and resolved.is_confirmed and resolved.reading:
                    current_run.update(
                        {
                            "survival_ms": resolved.reading.survival_ms,
                            "bullet_count": resolved.reading.bullet_count,
                            "score_confidence": resolved.reading.confidence,
                            "score_agreeing_frames": resolved.agreeing_frames,
                            "score_total_frames": resolved.total_frames,
                            "status": "score_confirmed",
                        }
                    )
                else:
                    current_run["status"] = "needs_review"
            elif observation.changed and observation.state == GameState.TITLE and current_run is not None:
                current_run["ended_index"] = event["index"]
                current_run["ended_elapsed_seconds"] = event["elapsed_seconds"]
                if current_run.get("status") == "score_confirmed":
                    current_run["status"] = "complete"
                runs.append(current_run)
                current_run = None
                consensus = None

            if observation.state == GameState.RESULT and consensus is not None:
                consensus.add(reader.read(last_image))

    if current_run is not None:
        current_run["status"] = "incomplete"
        runs.append(current_run)
    output = session / "run_replay.json"
    payload = {"session_id": session.name, "runs": runs}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
