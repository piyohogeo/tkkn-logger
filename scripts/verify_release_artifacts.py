"""Validate the structure and checksum of a portable GitHub Release payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_release(release_dir: Path, version: str, expected_tag: str | None = None) -> None:
    if expected_tag and expected_tag != f"v{version}":
        raise ValueError(f"Tag {expected_tag!r} does not match application version {version!r}")
    archive_name = f"Tokkun99Logger-v{version}-windows-x64.zip"
    archive = release_dir / archive_name
    checksums = release_dir / "SHA256SUMS.txt"
    if not archive.is_file() or not checksums.is_file():
        raise FileNotFoundError("Release ZIP and SHA256SUMS.txt are both required")

    checksum_line = checksums.read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s{2}(.+)", checksum_line)
    if match is None or match.group(2) != archive_name:
        raise ValueError("SHA256SUMS.txt must contain exactly the portable ZIP checksum")
    if match.group(1).casefold() != file_sha256(archive).casefold():
        raise ValueError("Release ZIP SHA-256 does not match SHA256SUMS.txt")

    required = {
        "Tokkun99Logger/Tokkun99Logger.exe",
        "Tokkun99Logger/README.txt",
        "Tokkun99Logger/VERSION.txt",
        "Tokkun99Logger/LICENSE",
        "Tokkun99Logger/THIRD_PARTY_ASSETS.md",
        "Tokkun99Logger/LICENSES/THIRD_PARTY_NOTICES.txt",
        "Tokkun99Logger/LICENSES/FFmpeg-LGPL-3.0-or-later.txt",
        "Tokkun99Logger/LICENSES/FFmpeg-BUILD.txt",
        "Tokkun99Logger/LICENSES/FFmpeg-MANIFEST.json",
        "Tokkun99Logger/LICENSES/FFmpeg-COMPONENTS.json",
        "Tokkun99Logger/LICENSES/FFmpeg-BUILD-RECIPES.json",
        "Tokkun99Logger/LICENSES/FFmpeg-RECIPE-LICENSES.json",
        "Tokkun99Logger/LICENSES/FFmpeg-NESTED-LICENSES.json",
        "Tokkun99Logger/LICENSES/FFmpeg-NESTED-DEPENDENCIES.json",
        "Tokkun99Logger/LICENSES/FFmpeg-VENDORED-LICENSES.json",
        "Tokkun99Logger/LICENSES/FFmpeg-VENDORED-CODE.json",
        "Tokkun99Logger/LICENSES/FFmpeg-ADDITIONAL-SOURCES.json",
        "Tokkun99Logger/LICENSES/RAV1E-CARGO-LICENSES.json",
        "Tokkun99Logger/LICENSES/RAV1E-Cargo.lock",
        "Tokkun99Logger/_internal/ffmpeg.exe",
    }
    with zipfile.ZipFile(archive) as package:
        files = {name for name in package.namelist() if not name.endswith("/")}
        missing = sorted(required - files)
        if missing:
            raise ValueError("Release ZIP is missing: " + ", ".join(missing))
        for name in files:
            path = PurePosixPath(name)
            if not path.parts or path.parts[0] != "Tokkun99Logger":
                raise ValueError(f"ZIP entry is outside Tokkun99Logger/: {name}")
            if path.is_absolute() or any(part in (".", "..") for part in path.parts):
                raise ValueError(f"ZIP entry has an unsafe path: {name}")
            if len(path.parts) > 1 and path.parts[1].casefold() == "data":
                raise ValueError(f"Release ZIP contains user data: {name}")
            if name.casefold().endswith((".mp4", ".incomplete", ".sqlite3", ".log")):
                raise ValueError(f"Release ZIP contains a runtime artifact: {name}")
        version_text = package.read("Tokkun99Logger/VERSION.txt").decode("utf-8").strip()
        if version_text != version:
            raise ValueError(f"VERSION.txt is {version_text!r}, expected {version!r}")
        recipe_manifest = json.loads(
            package.read("Tokkun99Logger/LICENSES/FFmpeg-RECIPE-LICENSES.json")
        )
        if recipe_manifest["recipe_root_notices_complete"] is not True:
            raise ValueError("Release ZIP has incomplete FFmpeg recipe root notices")
        for recipe in recipe_manifest["recipes"]:
            for item in recipe["license_files"]:
                relative = PurePosixPath(item["path"])
                if (
                    not relative.parts
                    or relative.parts[0] != "ffmpeg-recipe-licenses"
                    or ".." in relative.parts
                ):
                    raise ValueError(f"Unsafe FFmpeg recipe license path: {relative}")
                member = "Tokkun99Logger/LICENSES/" + relative.as_posix()
                if member not in files:
                    raise ValueError(f"Release ZIP is missing recipe license: {member}")
                if bytes_sha256(package.read(member)) != item["sha256"]:
                    raise ValueError(f"Release ZIP recipe license hash mismatch: {member}")
        nested_manifest = json.loads(
            package.read("Tokkun99Logger/LICENSES/FFmpeg-NESTED-LICENSES.json")
        )
        if nested_manifest["linked_nested_notices_complete"] is not True:
            raise ValueError("Release ZIP has incomplete linked nested notices")
        for dependency in nested_manifest["dependencies"]:
            items = dependency["license_files"]
            linked = dependency["classification"] in {"linked", "linked_generated"}
            if linked != bool(items):
                raise ValueError("Release ZIP nested notice classification mismatch")
            for item in items:
                relative = PurePosixPath(item["path"])
                if (
                    not relative.parts
                    or relative.parts[0] != "ffmpeg-nested-licenses"
                    or ".." in relative.parts
                ):
                    raise ValueError(f"Unsafe FFmpeg nested license path: {relative}")
                member = "Tokkun99Logger/LICENSES/" + relative.as_posix()
                if member not in files:
                    raise ValueError(f"Release ZIP is missing nested license: {member}")
                if bytes_sha256(package.read(member)) != item["sha256"]:
                    raise ValueError(f"Release ZIP nested license hash mismatch: {member}")
        vendored_manifest = json.loads(
            package.read("Tokkun99Logger/LICENSES/FFmpeg-VENDORED-LICENSES.json")
        )
        if vendored_manifest["vendored_code_review_complete"] is not True:
            raise ValueError("Release ZIP has an incomplete vendored-code review")
        for dependency in vendored_manifest["dependencies"]:
            items = dependency["license_files"]
            if (dependency["classification"] == "linked") != bool(items):
                raise ValueError("Release ZIP vendored notice classification mismatch")
            for item in items:
                relative = PurePosixPath(item["path"])
                if (
                    not relative.parts
                    or relative.parts[0] != "ffmpeg-vendored-licenses"
                    or ".." in relative.parts
                ):
                    raise ValueError(f"Unsafe FFmpeg vendored license path: {relative}")
                member = "Tokkun99Logger/LICENSES/" + relative.as_posix()
                if member not in files:
                    raise ValueError(f"Release ZIP is missing vendored license: {member}")
                if bytes_sha256(package.read(member)) != item["sha256"]:
                    raise ValueError(
                        f"Release ZIP vendored license hash mismatch: {member}"
                    )
        rav1e_manifest = json.loads(
            package.read("Tokkun99Logger/LICENSES/RAV1E-CARGO-LICENSES.json")
        )
        if rav1e_manifest.get("release_ready") is not True:
            raise ValueError("Release ZIP has a non-release-ready rav1e manifest")
        risk_acceptance = rav1e_manifest.get(
            "unattested_build_risk_acceptance", {}
        )
        if (
            rav1e_manifest["actual_build_lock_attested"] is not True
            and risk_acceptance.get("accepted") is not True
        ):
            raise ValueError(
                "Release ZIP has an unattested rav1e Cargo lockfile without "
                "documented risk acceptance"
            )
        if bytes_sha256(
            package.read("Tokkun99Logger/LICENSES/RAV1E-Cargo.lock")
        ) != rav1e_manifest["source_lock_sha256"]:
            raise ValueError("Release ZIP rav1e Cargo.lock hash mismatch")
        for dependency in rav1e_manifest["packages"]:
            items = dependency["license_files"]
            if (dependency["classification"] == "linked_candidate") != bool(items):
                raise ValueError("Release ZIP rav1e notice classification mismatch")
            for item in items:
                relative = PurePosixPath(item["path"])
                if (
                    not relative.parts
                    or relative.parts[0] != "rav1e-cargo-licenses"
                    or ".." in relative.parts
                ):
                    raise ValueError(f"Unsafe rav1e Cargo license path: {relative}")
                member = "Tokkun99Logger/LICENSES/" + relative.as_posix()
                if member not in files:
                    raise ValueError(f"Release ZIP is missing rav1e license: {member}")
                if bytes_sha256(package.read(member)) != item["sha256"]:
                    raise ValueError(
                        f"Release ZIP rav1e license hash mismatch: {member}"
                    )
        if rav1e_manifest.get("toolchain_notices_complete") is not True:
            raise ValueError("Release ZIP has incomplete Rust toolchain notices")
        for component in rav1e_manifest.get("toolchain_components", []):
            if not component["license_files"]:
                raise ValueError("Release ZIP is missing Rust toolchain notices")
            for item in component["license_files"]:
                relative = PurePosixPath(item["path"])
                if (
                    not relative.parts
                    or relative.parts[0] != "rav1e-cargo-licenses"
                    or ".." in relative.parts
                ):
                    raise ValueError(
                        f"Unsafe rav1e toolchain license path: {relative}"
                    )
                member = "Tokkun99Logger/LICENSES/" + relative.as_posix()
                if member not in files:
                    raise ValueError(
                        f"Release ZIP is missing rav1e toolchain license: {member}"
                    )
                if bytes_sha256(package.read(member)) != item["sha256"]:
                    raise ValueError(
                        f"Release ZIP rav1e toolchain license hash mismatch: {member}"
                    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-tag")
    args = parser.parse_args()
    verify_release(args.release_dir.resolve(), args.version, args.expected_tag)
    print(f"Verified Release artifacts in {args.release_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
