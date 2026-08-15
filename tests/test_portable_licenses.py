from __future__ import annotations

import json
from pathlib import Path

from scripts.collect_portable_licenses import is_license_file


def test_license_file_filter_accepts_notices_without_unrelated_xml() -> None:
    assert is_license_file("package.dist-info/licenses/LICENSE.txt")
    assert is_license_file("NOTICE.md")
    assert is_license_file("COPYING")
    assert not is_license_file("cv2/data/haarcascade_license_plate.xml")
    assert not is_license_file("module.py")


def test_ffmpeg_manifest_pins_reproducible_gpl_build() -> None:
    project = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (project / "packaging" / "ffmpeg-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["version"] == "4.3.1-2021-01-01-full_build-www.gyan.dev"
    assert manifest["license"] == "GPL-3.0"
    assert len(manifest["sha256"]) == 64
