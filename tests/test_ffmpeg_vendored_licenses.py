from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.collect_portable_licenses import verify_vendored_license_bundle


PROJECT = Path(__file__).resolve().parents[1]


def test_vendored_inventory_is_complete() -> None:
    inventory = json.loads(
        (PROJECT / "packaging" / "ffmpeg-vendored-code.json").read_text(
            encoding="utf-8"
        )
    )
    assert inventory["audited_recipe_count"] == 77
    assert inventory["audited_recipe_count"] == len(inventory["audited_recipes"])
    assert inventory["audited_recipes"] == sorted(set(inventory["audited_recipes"]))
    assert inventory["vendored_code_review_complete"] is True
    assert inventory["release_ready"] is False
    assert {item["classification"] for item in inventory["dependencies"]} == {
        "linked",
        "excluded",
        "build_tool",
    }


def test_vendored_license_hashes_and_classifications() -> None:
    notices = json.loads(
        (PROJECT / "packaging" / "ffmpeg-vendored-licenses.json").read_text(
            encoding="utf-8"
        )
    )
    assert notices["vendored_code_review_complete"] is True
    assert notices["release_ready"] is False
    assert notices["audited_recipe_count"] == len(notices["audited_recipes"])
    for dependency in notices["dependencies"]:
        files = dependency["license_files"]
        assert bool(files) is (dependency["classification"] == "linked")
        for item in files:
            path = PROJECT / "packaging" / item["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    verify_vendored_license_bundle(
        notices, PROJECT / "packaging" / "ffmpeg-vendored-licenses"
    )
