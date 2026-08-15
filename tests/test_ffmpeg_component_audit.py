from __future__ import annotations

from pathlib import Path

from scripts.audit_ffmpeg_component_licenses import LICENSE_NAME, safe_name


def test_component_names_are_converted_to_safe_cache_paths() -> None:
    assert safe_name("BtbN Vulkan Shim Loader") == "BtbN-Vulkan-Shim-Loader"
    assert safe_name("XZ Utils/liblzma") == "XZ-Utils-liblzma"


def test_license_candidate_pattern_accepts_common_notice_names() -> None:
    accepted = ("LICENSE", "LICENSE.md", "COPYING.LGPLv3", "NOTICE", "PATENTS.txt")
    rejected = (
        "license_check.py",
        "license-checker.cfg",
        "license-check.sh",
        "license_plate.xml",
        "README.md",
    )

    assert all(LICENSE_NAME.fullmatch(Path(name).name) for name in accepted)
    assert all(LICENSE_NAME.fullmatch(Path(name).name) is None for name in rejected)
