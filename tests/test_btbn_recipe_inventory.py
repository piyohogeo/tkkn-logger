from __future__ import annotations

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def test_fixed_btbn_recipe_inventory_includes_known_transitive_dependencies() -> None:
    inventory = json.loads(
        (PROJECT / "packaging" / "ffmpeg-build-recipes.json").read_text(encoding="utf-8")
    )
    recipes = {entry["recipe"]: entry for entry in inventory["recipes"]}
    additional = {entry["id"]: entry for entry in inventory["additional_sources"]}

    assert inventory["target"] == "win64"
    assert inventory["variant"] == "lgpl"
    assert inventory["ffmpeg_addin"] == "8.1"
    assert inventory["release_ready"] is True
    assert len(recipes) >= 70
    assert recipes["scripts.d/25-fftw3.sh"]["revision"] == (
        "93ed4c786934aec9946f8dda4b4e3eb08f8be41c"
    )
    assert recipes["scripts.d/50-librist/40-mbedtls.sh"]["revision"] == "v4.1.0"
    assert recipes["scripts.d/50-libmp3lame.sh"]["revision"] == "6531"
    assert recipes["scripts.d/50-lilv/96-serd.sh"]["repository"].endswith("/serd.git")
    assert len(additional) == 6
    assert additional["scripts.d/20-libiconv.sh#source2"]["revision"] == (
        "103c922f47f8b0fb0503024783bdaff5016eea82"
    )
    assert additional["scripts.d/45-opencl.sh#source2"]["repository"].endswith(
        "/OpenCL-ICD-Loader.git"
    )
    assert additional["scripts.d/50-ffnvcodec.sh#source2"]["revision"] == (
        "33a9ede8d9914299d9262539c576a15bd0a19621"
    )
    assert additional["scripts.d/50-libopus.sh#opus-data"]["revision"] == (
        "a5177ec6fb7d15058e99e57029746100121f68e4890b1467d4094aa336b6013e"
    )
    assert additional["scripts.d/50-libopus.sh#opus-data"]["notice_required"] is False


def test_recipe_inventory_has_no_floating_source_revisions() -> None:
    inventory = json.loads(
        (PROJECT / "packaging" / "ffmpeg-build-recipes.json").read_text(encoding="utf-8")
    )

    assert all(entry["revision"] not in {"main", "master", "HEAD"} for entry in inventory["recipes"])
    assert len({entry["recipe"] for entry in inventory["recipes"]}) == len(inventory["recipes"])
    assert len({entry["id"] for entry in inventory["additional_sources"]}) == len(
        inventory["additional_sources"]
    )
    for entry in inventory["recipes"] + inventory["additional_sources"]:
        revision = entry["revision"]
        if len(revision) == 40:
            continue
        if len(revision) == 64 and entry["repository"].endswith(".tar.gz"):
            continue
        if entry["repository"].startswith("https://svn.") and revision.isdecimal():
            continue
        assert len(entry["resolved_revision"]) == 40
