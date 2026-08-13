"""Build versioned glyph templates from reviewed RESULT frames and values."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.result_reader import (  # noqa: E402
    extract_components,
    select_bullet_components,
    select_survival_components,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "templates" / "glyphs" / "v1"
BUILD_ROIS = {"survival": (120, 118, 230, 138), "bullets": (120, 143, 220, 162)}
PROFILE_ROIS = {
    "survival": [120, 118, 230, 138],
    "bullets": [[120, 143, 220, 162], [120, 169, 220, 188]],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument(
        "--sample",
        action="append",
        required=True,
        help="Reviewed INDEX:SURVIVAL_TEXT:BULLET_TEXT, e.g. 233:9.408:51",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    profile_path = args.output / "profile.json"
    existing = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else None
    template_paths: dict[str, set[str]] = {
        label: set(paths) for label, paths in (existing or {}).get("templates", {}).items()
    }
    reviewed_samples = list((existing or {}).get("source", {}).get("reviewed_samples", []))
    session_ids = set((existing or {}).get("source", {}).get("session_ids", []))
    old_session_id = (existing or {}).get("source", {}).get("session_id")
    if old_session_id:
        session_ids.add(old_session_id)
    session_ids.add(args.session.name)
    for specification in args.sample:
        index_text, survival_text, bullet_text = specification.split(":", 2)
        index = int(index_text)
        image_path = args.session.resolve() / "frames" / f"{index:06d}.png"
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise SystemExit(f"Frame not found: {image_path}")
        for roi_name, expected, allow_decimal in (
            ("survival", survival_text, True),
            ("bullets", bullet_text, False),
        ):
            left, top, right, bottom = BUILD_ROIS[roi_name]
            components = extract_components(frame[top:bottom, left:right], allow_decimal)
            if roi_name == "survival":
                components = select_survival_components(components)
            else:
                components = select_bullet_components(components)[: len(expected)]
            glyphs = [component.glyph for component in components]
            if len(glyphs) != len(expected):
                raise SystemExit(
                    f"{image_path.name} {roi_name}: extracted {len(glyphs)}, expected {len(expected)}"
                )
            for label, glyph in zip(expected, glyphs):
                safe_label = "dot" if label == "." else label
                label_dir = args.output / safe_label
                label_dir.mkdir(exist_ok=True)
                digest = hashlib.sha256(glyph.tobytes()).hexdigest()[:12]
                relative = f"{safe_label}/{digest}.png"
                output_path = args.output / relative
                cv2.imwrite(str(output_path), glyph.astype("uint8") * 255)
                template_paths.setdefault(label, set()).add(relative)
        sample_record = {
            "session_id": args.session.name,
            "index": index,
            "survival_text": survival_text,
            "bullet_text": bullet_text,
        }
        if sample_record not in reviewed_samples:
            reviewed_samples.append(sample_record)
    profile = {
        "profile_version": 2,
        "reference_size": [320, 240],
        "minimum_confidence": 0.95,
        "minimum_margin": 0.05,
        "maximum_shift": 1,
        "rois": PROFILE_ROIS,
        "templates": {label: sorted(paths) for label, paths in sorted(template_paths.items())},
        "source": {"session_ids": sorted(session_ids), "reviewed_samples": reviewed_samples},
        "missing_digits": sorted(set("0123456789") - set(template_paths)),
    }
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(profile_path)
    print("Missing digits:", ", ".join(profile["missing_digits"]) or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
