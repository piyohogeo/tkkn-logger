from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.verify_release_artifacts import verify_release


def make_release(
    tmp_path: Path,
    version: str = "0.1.0",
    *,
    vendored_complete: bool = True,
    rav1e_attested: bool = True,
    rav1e_risk_accepted: bool = False,
) -> Path:
    release = tmp_path / "release"
    release.mkdir()
    archive = release / f"Tokkun99Logger-v{version}-windows-x64.zip"
    recipe_license = b"license"
    recipe_manifest = {
        "recipe_root_notices_complete": True,
        "recipes": [
            {
                "license_files": [
                    {
                        "path": "ffmpeg-recipe-licenses/test/LICENSE",
                        "sha256": hashlib.sha256(recipe_license).hexdigest(),
                    }
                ]
            }
        ],
    }
    nested_license = b"nested-license"
    nested_manifest = {
        "linked_nested_notices_complete": True,
        "dependencies": [
            {
                "classification": "linked",
                "license_files": [
                    {
                        "path": "ffmpeg-nested-licenses/test/LICENSE",
                        "sha256": hashlib.sha256(nested_license).hexdigest(),
                    }
                ],
            }
        ],
    }
    vendored_license = b"vendored-license"
    vendored_manifest = {
        "vendored_code_review_complete": vendored_complete,
        "dependencies": [
            {
                "classification": "linked",
                "license_files": [
                    {
                        "path": "ffmpeg-vendored-licenses/test/LICENSE",
                        "sha256": hashlib.sha256(vendored_license).hexdigest(),
                    }
                ],
            }
        ],
    }
    rav1e_license = b"rav1e-license"
    rust_toolchain_license = b"rust-toolchain-license"
    rav1e_lock = b"rav1e-lock"
    rav1e_manifest = {
        "release_ready": True,
        "actual_build_lock_attested": rav1e_attested,
        "unattested_build_risk_acceptance": {
            "accepted": rav1e_risk_accepted,
        },
        "source_lock_sha256": hashlib.sha256(rav1e_lock).hexdigest(),
        "toolchain_notices_complete": True,
        "packages": [
            {
                "classification": "linked_candidate",
                "license_files": [
                    {
                        "path": "rav1e-cargo-licenses/test/LICENSE",
                        "sha256": hashlib.sha256(rav1e_license).hexdigest(),
                    }
                ],
            }
        ],
        "toolchain_components": [
            {
                "license_files": [
                    {
                        "path": "rav1e-cargo-licenses/rust-std/LICENSE",
                        "sha256": hashlib.sha256(
                            rust_toolchain_license
                        ).hexdigest(),
                    }
                ]
            }
        ],
    }
    entries = {
        "Tokkun99Logger/Tokkun99Logger.exe": b"exe",
        "Tokkun99Logger/README.txt": b"readme",
        "Tokkun99Logger/VERSION.txt": version.encode() + b"\n",
        "Tokkun99Logger/LICENSE": b"MIT",
        "Tokkun99Logger/THIRD_PARTY_ASSETS.md": b"assets",
        "Tokkun99Logger/LICENSES/THIRD_PARTY_NOTICES.txt": b"notices",
        "Tokkun99Logger/LICENSES/FFmpeg-LGPL-3.0-or-later.txt": b"lgpl",
        "Tokkun99Logger/LICENSES/FFmpeg-BUILD.txt": b"build",
        "Tokkun99Logger/LICENSES/FFmpeg-MANIFEST.json": b"{}",
        "Tokkun99Logger/LICENSES/FFmpeg-COMPONENTS.json": b"{}",
        "Tokkun99Logger/LICENSES/FFmpeg-BUILD-RECIPES.json": b"{}",
        "Tokkun99Logger/LICENSES/FFmpeg-RECIPE-LICENSES.json": json.dumps(
            recipe_manifest
        ).encode(),
        "Tokkun99Logger/LICENSES/ffmpeg-recipe-licenses/test/LICENSE": recipe_license,
        "Tokkun99Logger/LICENSES/FFmpeg-NESTED-LICENSES.json": json.dumps(
            nested_manifest
        ).encode(),
        "Tokkun99Logger/LICENSES/FFmpeg-NESTED-DEPENDENCIES.json": b"{}",
        "Tokkun99Logger/LICENSES/ffmpeg-nested-licenses/test/LICENSE": nested_license,
        "Tokkun99Logger/LICENSES/FFmpeg-VENDORED-LICENSES.json": json.dumps(
            vendored_manifest
        ).encode(),
        "Tokkun99Logger/LICENSES/FFmpeg-VENDORED-CODE.json": b"{}",
        "Tokkun99Logger/LICENSES/FFmpeg-ADDITIONAL-SOURCES.json": b"{}",
        "Tokkun99Logger/LICENSES/ffmpeg-vendored-licenses/test/LICENSE": vendored_license,
        "Tokkun99Logger/LICENSES/RAV1E-CARGO-LICENSES.json": json.dumps(
            rav1e_manifest
        ).encode(),
        "Tokkun99Logger/LICENSES/RAV1E-Cargo.lock": rav1e_lock,
        "Tokkun99Logger/LICENSES/rav1e-cargo-licenses/test/LICENSE": rav1e_license,
        "Tokkun99Logger/LICENSES/rav1e-cargo-licenses/rust-std/LICENSE": rust_toolchain_license,
        "Tokkun99Logger/_internal/ffmpeg.exe": b"ffmpeg",
        "Tokkun99Logger/_internal/cv2/data/__init__.py": b"",
    }
    with zipfile.ZipFile(archive, "w") as package:
        for name, content in entries.items():
            package.writestr(name, content)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / "SHA256SUMS.txt").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    return release


def test_release_artifacts_require_parent_folder_version_and_checksum(tmp_path: Path) -> None:
    release = make_release(tmp_path)
    verify_release(release, "0.1.0", "v0.1.0")


def test_release_artifacts_reject_data_and_tag_mismatch(tmp_path: Path) -> None:
    release = make_release(tmp_path)
    archive = release / "Tokkun99Logger-v0.1.0-windows-x64.zip"
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("Tokkun99Logger/data/log/logger.sqlite3", b"db")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / "SHA256SUMS.txt").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="user data"):
        verify_release(release, "0.1.0")
    with pytest.raises(ValueError, match="does not match"):
        verify_release(release, "0.1.0", "v0.2.0")


def test_release_artifacts_reject_incomplete_vendored_review(tmp_path: Path) -> None:
    release = make_release(tmp_path, vendored_complete=False)

    with pytest.raises(ValueError, match="incomplete vendored-code"):
        verify_release(release, "0.1.0")


def test_release_artifacts_reject_unattested_rav1e_lock(tmp_path: Path) -> None:
    release = make_release(tmp_path, rav1e_attested=False)

    with pytest.raises(ValueError, match="unattested rav1e"):
        verify_release(release, "0.1.0")


def test_release_artifacts_accept_documented_rav1e_risk(tmp_path: Path) -> None:
    release = make_release(
        tmp_path,
        rav1e_attested=False,
        rav1e_risk_accepted=True,
    )

    verify_release(release, "0.1.0")


def test_release_artifacts_reject_unsafe_zip_paths(tmp_path: Path) -> None:
    release = make_release(tmp_path)
    archive = release / "Tokkun99Logger-v0.1.0-windows-x64.zip"
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("Tokkun99Logger/../outside.txt", b"unsafe")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / "SHA256SUMS.txt").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="unsafe path"):
        verify_release(release, "0.1.0")
