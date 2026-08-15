from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.collect_portable_licenses import verify_nested_license_bundle


PROJECT = Path(__file__).resolve().parents[1]


def test_linked_nested_dependencies_have_staged_notices() -> None:
    inventory = json.loads(
        (PROJECT / "packaging" / "ffmpeg-nested-dependencies.json").read_text(
            encoding="utf-8"
        )
    )
    notices = json.loads(
        (PROJECT / "packaging" / "ffmpeg-nested-licenses.json").read_text(
            encoding="utf-8"
        )
    )
    by_name = {entry["recipe"]: entry for entry in notices["dependencies"]}

    assert notices["linked_nested_notices_complete"] is True
    assert notices["vendored_code_review_complete"] is True
    assert notices["release_ready"] is True
    for dependency in inventory["recipes"]:
        staged = by_name[dependency["recipe"]]["license_files"]
        if dependency["classification"] in {"linked", "linked_generated"}:
            assert staged
        else:
            assert staged == []


def test_staged_nested_license_hashes_match_manifest() -> None:
    notices = json.loads(
        (PROJECT / "packaging" / "ffmpeg-nested-licenses.json").read_text(
            encoding="utf-8"
        )
    )
    for dependency in notices["dependencies"]:
        for item in dependency["license_files"]:
            path = PROJECT / "packaging" / item["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    verify_nested_license_bundle(
        notices, PROJECT / "packaging" / "ffmpeg-nested-licenses"
    )
