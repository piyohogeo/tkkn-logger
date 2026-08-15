"""Verify the pinned FFmpeg archive and extracted Windows binary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pe_machine(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise ValueError(f"Not a Windows PE executable: {path}")
        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        stream.seek(pe_offset)
        pe_header = stream.read(6)
    if len(pe_header) != 6 or pe_header[:4] != b"PE\0\0":
        raise ValueError(f"Invalid PE header: {path}")
    return struct.unpack_from("<H", pe_header, 4)[0]


def run_tool(path: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [path, "-hide_banner", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return completed.stdout + completed.stderr


def verify(manifest_path: Path, ffmpeg_root: Path, archive: Path | None = None) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ffmpeg = ffmpeg_root / "bin" / "ffmpeg.exe"
    ffprobe = ffmpeg_root / "bin" / "ffprobe.exe"
    license_path = ffmpeg_root / manifest["license_file"]
    for required in (ffmpeg, ffprobe, license_path):
        if not required.is_file():
            raise FileNotFoundError(f"Required FFmpeg input not found: {required}")

    if archive is not None:
        actual_archive_hash = sha256(archive)
        if actual_archive_hash.casefold() != manifest["archive_sha256"].casefold():
            raise ValueError(f"FFmpeg archive SHA-256 mismatch: {actual_archive_hash}")

    actual_ffmpeg_hash = sha256(ffmpeg)
    if actual_ffmpeg_hash.casefold() != manifest["ffmpeg_sha256"].casefold():
        raise ValueError(f"ffmpeg.exe SHA-256 mismatch: {actual_ffmpeg_hash}")
    if pe_machine(ffmpeg) != 0x8664:
        raise ValueError("FFmpeg is not a Windows x64 executable")

    version_output = run_tool(ffmpeg, "-version")
    configure_line = next(
        (line for line in version_output.splitlines() if line.startswith("configuration:")),
        "",
    )
    if manifest["version"] not in version_output:
        raise ValueError("FFmpeg version does not match the pinned manifest")
    for forbidden in ("--enable-gpl", "--enable-nonfree"):
        if forbidden in configure_line:
            raise ValueError(f"Forbidden FFmpeg configure option: {forbidden}")
    for required_option in ("--arch=x86_64", "--target-os=mingw32", "--enable-version3"):
        if required_option not in configure_line:
            raise ValueError(f"Required FFmpeg configure option is missing: {required_option}")

    encoders_output = run_tool(ffmpeg, "-encoders")
    if re.search(r"^\s*V\S*\s+mpeg4\s", encoders_output, re.MULTILINE) is None:
        raise ValueError("FFmpeg standard mpeg4 encoder is unavailable")
    encoder_help = run_tool(ffmpeg, "-h", "encoder=mpeg4")
    if "Encoder mpeg4 [MPEG-4 part 2]" not in encoder_help:
        raise ValueError("Unexpected FFmpeg mpeg4 encoder implementation")

    license_text = license_path.read_text(encoding="utf-8", errors="replace")
    if "GNU LESSER GENERAL PUBLIC LICENSE" not in license_text or "Version 3" not in license_text:
        raise ValueError("Expected the FFmpeg LGPL version 3 license text")

    return {
        "ffmpeg": str(ffmpeg),
        "ffprobe": str(ffprobe),
        "ffmpeg_sha256": actual_ffmpeg_hash,
        "version_output": version_output,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ffmpeg-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()

    result = verify(
        args.manifest.resolve(),
        args.ffmpeg_root.resolve(),
        args.archive.resolve() if args.archive else None,
    )
    print(f"Verified LGPL FFmpeg: {result['ffmpeg']}")
    print(f"ffmpeg.exe SHA-256: {result['ffmpeg_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
