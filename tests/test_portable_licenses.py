from __future__ import annotations

import json
from pathlib import Path
import struct

from scripts.collect_portable_licenses import FFMPEG_LICENSE_OUTPUT, is_license_file
from scripts.verify_ffmpeg_distribution import pe_machine, sha256


def test_license_file_filter_accepts_notices_without_unrelated_xml() -> None:
    assert is_license_file("package.dist-info/licenses/LICENSE.txt")
    assert is_license_file("NOTICE.md")
    assert is_license_file("COPYING")
    assert not is_license_file("cv2/data/haarcascade_license_plate.xml")
    assert not is_license_file("module.py")


def test_ffmpeg_verifier_hashes_files_and_requires_windows_x64_pe(tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    image = bytearray(128)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 64)
    image[64:68] = b"PE\0\0"
    struct.pack_into("<H", image, 68, 0x8664)
    executable.write_bytes(image)

    assert pe_machine(executable) == 0x8664
    assert sha256(executable) == "d1a163b6d2e1ca2d24467cc99302770cca68a3bcc2e610f724fca69b410dd19a"


def test_ffmpeg_manifest_pins_reproducible_lgpl_build() -> None:
    project = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (project / "packaging" / "ffmpeg-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["version"] == "n8.1.2-34-g9b6c8969e0"
    assert manifest["variant"] == "win64-lgpl-8.1"
    assert manifest["license"] == "LGPL-3.0-or-later"
    assert len(manifest["archive_sha256"]) == 64
    assert len(manifest["ffmpeg_sha256"]) == 64
    assert "/tree/9b6c8969e05b4f0b29f0f85cd501be6b3e582e6b" in manifest["ffmpeg_source_url"]
    assert "/tree/a99e8230eae00d1cee38f23076a7a1f55cd984e2" in manifest["build_source_url"]
    assert FFMPEG_LICENSE_OUTPUT == "FFmpeg-LGPL-3.0-or-later.txt"


def test_ffmpeg_component_audit_covers_each_configure_flag_once_or_more() -> None:
    project = Path(__file__).resolve().parents[1]
    components = json.loads(
        (project / "packaging" / "ffmpeg-components.json").read_text(encoding="utf-8")
    )

    audited = set(components["audited_configure_flags"])
    represented = {
        flag
        for component in components["components"]
        for flag in component["configure_flags"]
    }

    assert audited
    assert represented == audited
    assert {"chromaprint", "ffnvcodec"} <= audited
    assert set(components["non_component_enable_flags"]) == {"version3", "pthreads"}
    assert all(component["revision"] for component in components["components"])
    assert all(component["license"] for component in components["components"])
    assert all(component["source_repository"] for component in components["components"])


def test_ffmpeg_component_audit_blocks_release_until_notices_are_complete() -> None:
    project = Path(__file__).resolve().parents[1]
    components = json.loads(
        (project / "packaging" / "ffmpeg-components.json").read_text(encoding="utf-8")
    )

    assert components["release_ready"] is False
    assert components["blocking_reason"]
    assert any(component["notice_file"] is None for component in components["components"])


def test_project_mit_license_has_expected_copyright() -> None:
    project = Path(__file__).resolve().parents[1]
    license_text = (project / "LICENSE").read_text(encoding="utf-8")

    assert license_text.startswith("MIT License\n\nCopyright (c) 2026 piyohogeo\n")
    assert "Permission is hereby granted, free of charge" in license_text
