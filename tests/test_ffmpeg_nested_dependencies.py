from __future__ import annotations

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def test_nested_dependency_inventory_has_fixed_revisions_and_classifications() -> None:
    inventory = json.loads(
        (PROJECT / "packaging" / "ffmpeg-nested-dependencies.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {entry["recipe"]: entry for entry in inventory["recipes"]}

    assert inventory["release_ready"] is True
    assert len(entries) == len(inventory["recipes"])
    assert all(len(entry["revision"]) == 40 for entry in entries.values())
    assert {entry["classification"] for entry in entries.values()} == {
        "linked",
        "linked_generated",
        "build_tool",
        "excluded",
    }
    assert entries["shaderc/glslang"]["classification"] == "linked"
    assert entries["shaderc/googletest"]["classification"] == "excluded"
    assert entries["zimg/graphengine"]["classification"] == "linked"
    assert entries["openssl/gost-engine"]["classification"] == "excluded"


def test_every_linked_nested_dependency_has_evidence() -> None:
    inventory = json.loads(
        (PROJECT / "packaging" / "ffmpeg-nested-dependencies.json").read_text(
            encoding="utf-8"
        )
    )

    linked = [
        entry
        for entry in inventory["recipes"]
        if entry["classification"] in {"linked", "linked_generated"}
    ]
    assert linked
    assert all(entry["evidence"] for entry in linked)
