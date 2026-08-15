from __future__ import annotations

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def test_all_additional_recipe_sources_are_fixed_and_classified() -> None:
    recipes = json.loads(
        (PROJECT / "packaging" / "ffmpeg-build-recipes.json").read_text(
            encoding="utf-8"
        )
    )
    classification = json.loads(
        (
            PROJECT
            / "packaging"
            / "ffmpeg-additional-source-classification.json"
        ).read_text(encoding="utf-8")
    )
    expected = {item["id"] for item in recipes["additional_sources"]}
    expected.add("scripts.d/50-ffnvcodec.sh#source1")
    actual = {item["id"] for item in classification["sources"]}

    assert len(recipes["recipes"]) == 77
    assert len(recipes["additional_sources"]) == 6
    assert actual == expected
    assert classification["review_complete"] is True
    assert classification["release_ready"] is True
    assert all(
        item["classification"]
        in {"linked", "linked_generated", "build_tool", "excluded"}
        for item in classification["sources"]
    )
    classifications = {item["id"]: item["classification"] for item in classification["sources"]}
    assert all(
        classifications[item["id"]] == "excluded"
        for item in recipes["additional_sources"]
        if not item.get("notice_required", True)
    )
    assert (
        classifications["scripts.d/20-libiconv.sh#source2"] == "build_tool"
    )
