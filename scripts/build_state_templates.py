"""Build local binary state templates from a reviewed calibration session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "templates" / "states" / "v1"
ROIS = {
    "title": [(60, 20, 260, 125), (60, 185, 260, 235)],
    "result": [(55, 20, 270, 120)],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--title-index", type=int, required=True)
    parser.add_argument("--result-index", type=int, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frames = args.session.resolve() / "frames"
    sources = {
        "title": frames / f"{args.title_index:06d}.png",
        "result": frames / f"{args.result_index:06d}.png",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    templates: dict[str, list[dict[str, object]]] = {"title": [], "result": []}
    for state_name, source_path in sources.items():
        source = cv2.imread(str(source_path), cv2.IMREAD_GRAYSCALE)
        if source is None:
            raise SystemExit(f"Reference frame not found: {source_path}")
        for number, (left, top, right, bottom) in enumerate(ROIS[state_name]):
            output_name = f"{state_name}_{number}.png"
            binary = ((source[top:bottom, left:right] >= 180) * 255).astype("uint8")
            if not cv2.imwrite(str(args.output / output_name), binary):
                raise OSError(f"Could not write {output_name}")
            templates[state_name].append({"roi": [left, top, right, bottom], "path": output_name})
    profile = {
        "profile_version": 1,
        "reference_size": [320, 240],
        "text_threshold": 180,
        "title_threshold": 0.90,
        "result_threshold": 0.90,
        "stable_frames": 3,
        "templates": templates,
        "source": {
            "session_id": args.session.name,
            "title_index": args.title_index,
            "result_index": args.result_index,
        },
    }
    (args.output / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output / "profile.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
