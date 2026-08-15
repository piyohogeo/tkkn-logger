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
