from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.collect_portable_licenses import verify_recipe_license_bundle


PROJECT = Path(__file__).resolve().parents[1]


def test_every_btbn_source_recipe_has_staged_root_notices() -> None:
    recipes = json.loads(
        (PROJECT / "packaging" / "ffmpeg-build-recipes.json").read_text(encoding="utf-8")
    )
    notices = json.loads(
        (PROJECT / "packaging" / "ffmpeg-recipe-licenses.json").read_text(encoding="utf-8")
    )

    expected = {entry["recipe"] for entry in recipes["recipes"]}
    expected.update(
        entry["id"]
        for entry in recipes["additional_sources"]
        if entry.get("notice_required", True)
    )
    actual = {entry["recipe"] for entry in notices["recipes"]}
    assert actual == expected
    assert notices["recipe_root_notices_complete"] is True
    assert notices["nested_dependency_review_complete"] is True
    assert notices["release_ready"] is True
    assert all(entry["license_files"] for entry in notices["recipes"])


def test_staged_ffmpeg_recipe_license_hashes_match_manifest() -> None:
    notices = json.loads(
        (PROJECT / "packaging" / "ffmpeg-recipe-licenses.json").read_text(encoding="utf-8")
    )

    for recipe in notices["recipes"]:
        for item in recipe["license_files"]:
            path = PROJECT / "packaging" / item["path"]
            assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    verify_recipe_license_bundle(
        notices, PROJECT / "packaging" / "ffmpeg-recipe-licenses"
    )
