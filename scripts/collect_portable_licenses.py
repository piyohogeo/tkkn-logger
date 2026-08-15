"""Collect license files for software included in the portable build."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil


DISTRIBUTIONS = (
    "numpy",
    "opencv-python",
    "mss",
    "windows-capture",
    "pywin32",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
)
LICENSE_MARKERS = ("license", "licence", "copying", "notice")


def is_license_file(relative: str) -> bool:
    name = Path(relative).name.casefold()
    return any(marker in name for marker in LICENSE_MARKERS) and not name.endswith(".xml")


def collect_distribution_licenses(output: Path) -> list[str]:
    copied: list[str] = []
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        dependency_dir = output / f"{name}-{distribution.version}"
        for relative in distribution.files or ():
            relative_text = str(relative)
            if not is_license_file(relative_text):
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file():
                continue
            safe_parts = [
                part.replace(":", "_")
                for part in Path(relative_text).parts
                if part not in (".", "..")
            ]
            target = dependency_dir.joinpath(*safe_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(output).as_posix())
    return copied


def write_notices(output: Path, ffmpeg_readme: Path, ffmpeg_manifest: dict[str, str]) -> None:
    lines = [
        "Tokkun '99 Logger - Third-party software notices",
        "",
        "The portable directory includes the following third-party software.",
        "Full license texts are stored below this directory.",
        "",
    ]
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        home = distribution.metadata.get("Home-page") or "(see package metadata)"
        lines.append(f"- {name} {distribution.version}: {home}")
    lines.extend(
        [
            f"- FFmpeg {ffmpeg_manifest['version']}: {ffmpeg_manifest['build_url']}",
            f"  License: {ffmpeg_manifest['license']}; source: {ffmpeg_manifest['source_url']}",
            "",
            "FFmpeg build information:",
            ffmpeg_readme.read_text(encoding="utf-8"),
        ]
    )
    (output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg-root", type=Path, required=True)
    parser.add_argument("--ffmpeg-manifest", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    ffmpeg_root = args.ffmpeg_root.resolve()
    ffmpeg_license = ffmpeg_root / "LICENSE"
    ffmpeg_readme = ffmpeg_root / "README.txt"
    ffmpeg_manifest_path = args.ffmpeg_manifest.resolve()
    if not ffmpeg_license.is_file() or not ffmpeg_readme.is_file():
        raise FileNotFoundError("FFmpeg LICENSE and README.txt are required")

    output.mkdir(parents=True, exist_ok=True)
    ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
    collect_distribution_licenses(output)
    shutil.copy2(ffmpeg_license, output / "FFmpeg-GPL-3.0.txt")
    shutil.copy2(ffmpeg_readme, output / "FFmpeg-BUILD.txt")
    shutil.copy2(ffmpeg_manifest_path, output / "FFmpeg-MANIFEST.json")
    write_notices(output, ffmpeg_readme, ffmpeg_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
