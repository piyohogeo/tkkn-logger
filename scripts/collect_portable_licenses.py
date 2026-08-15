"""Collect license files for software included in the portable build."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess


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
FFMPEG_LICENSE_OUTPUT = "FFmpeg-LGPL-3.0-or-later.txt"


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


def capture_ffmpeg_build_info(ffmpeg: Path, ffmpeg_manifest: dict[str, str]) -> str:
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return "\n".join(
        [
            f"Provider: {ffmpeg_manifest['provider']}",
            f"Version: {ffmpeg_manifest['version']}",
            f"Variant: {ffmpeg_manifest['variant']}",
            f"Archive: {ffmpeg_manifest['archive_url']}",
            f"FFmpeg source: {ffmpeg_manifest['ffmpeg_source_url']}",
            f"Build source: {ffmpeg_manifest['build_source_url']}",
            f"ffmpeg.exe SHA-256: {ffmpeg_manifest['ffmpeg_sha256']}",
            "",
            "ffmpeg.exe -hide_banner -version:",
            (completed.stdout + completed.stderr).strip(),
            "",
        ]
    )


def write_notices(output: Path, ffmpeg_manifest: dict[str, str]) -> None:
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
            f"- FFmpeg {ffmpeg_manifest['version']} ({ffmpeg_manifest['variant']})",
            f"  Provider: {ffmpeg_manifest['provider']}",
            f"  License: {ffmpeg_manifest['license']}",
            f"  FFmpeg source: {ffmpeg_manifest['ffmpeg_source_url']}",
            f"  Build source: {ffmpeg_manifest['build_source_url']}",
            f"  ffmpeg.exe SHA-256: {ffmpeg_manifest['ffmpeg_sha256']}",
            "  FFmpeg runs as a separate process and is not linked into this application.",
            "  See FFmpeg-BUILD.txt and FFmpeg-MANIFEST.json for reproducible build details.",
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
    ffmpeg_manifest_path = args.ffmpeg_manifest.resolve()
    ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
    ffmpeg = ffmpeg_root / "bin" / "ffmpeg.exe"
    ffmpeg_license = ffmpeg_root / ffmpeg_manifest["license_file"]
    if not ffmpeg.is_file() or not ffmpeg_license.is_file():
        raise FileNotFoundError("Verified FFmpeg executable and license are required")

    output.mkdir(parents=True, exist_ok=True)
    collect_distribution_licenses(output)
    shutil.copy2(ffmpeg_license, output / FFMPEG_LICENSE_OUTPUT)
    (output / "FFmpeg-BUILD.txt").write_text(
        capture_ffmpeg_build_info(ffmpeg, ffmpeg_manifest), encoding="utf-8"
    )
    shutil.copy2(ffmpeg_manifest_path, output / "FFmpeg-MANIFEST.json")
    write_notices(output, ffmpeg_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
