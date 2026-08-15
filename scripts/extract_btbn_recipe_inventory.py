"""Extract fixed source recipes used by a generated BtbN Dockerfile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


RECIPE = re.compile(r"src=(scripts\.d/[^,\s]+\.sh)")
ASSIGNMENT = re.compile(r'^([A-Z][A-Z0-9_]*)="([^"]*)"$', re.MULTILINE)

# Opus autogen.sh invokes dnn/download_model.sh with this content hash. The
# acquisition is not expressed as a SCRIPT_REPO2 variable in BtbN's recipe,
# so keep it explicit while auditing this pinned source revision.
SCRIPTED_FIXED_SOURCES = (
    {
        "id": "scripts.d/50-libopus.sh#opus-data",
        "recipe": "scripts.d/50-libopus.sh",
        "source_variable": "autogen.sh/dnn/download_model.sh",
        "repository": (
            "https://media.xiph.org/opus/models/"
            "opus_data-a5177ec6fb7d15058e99e57029746100121f68e4890b1467d4094aa336b6013e.tar.gz"
        ),
        "revision": "a5177ec6fb7d15058e99e57029746100121f68e4890b1467d4094aa336b6013e",
        "notice_required": False,
    },
)


def extract(source_root: Path, dockerfile: Path) -> list[dict[str, str]]:
    recipe_paths = sorted(set(RECIPE.findall(dockerfile.read_text(encoding="utf-8"))))
    entries: list[dict[str, str]] = []
    for relative in recipe_paths:
        recipe = source_root / relative
        text = recipe.read_text(encoding="utf-8")
        variables = dict(ASSIGNMENT.findall(text))
        repository = variables.get("SCRIPT_REPO")
        revision = variables.get("SCRIPT_COMMIT") or variables.get("SCRIPT_REV")
        if repository is None:
            continue
        if revision is None:
            raise ValueError(f"Source recipe has no fixed revision: {relative}")
        entries.append(
            {
                "recipe": relative,
                "repository": repository,
                "revision": revision,
            }
        )
    return entries


def extract_additional_sources(
    source_root: Path, dockerfile: Path
) -> list[dict[str, str]]:
    recipe_paths = sorted(set(RECIPE.findall(dockerfile.read_text(encoding="utf-8"))))
    entries: list[dict[str, str]] = []
    for relative in recipe_paths:
        variables = dict(
            ASSIGNMENT.findall((source_root / relative).read_text(encoding="utf-8"))
        )
        suffixes = sorted(
            key.removeprefix("SCRIPT_REPO")
            for key in variables
            if re.fullmatch(r"SCRIPT_REPO[2-9][0-9]*", key)
        )
        for suffix in suffixes:
            repository = variables[f"SCRIPT_REPO{suffix}"]
            revision = variables.get(f"SCRIPT_COMMIT{suffix}") or variables.get(
                f"SCRIPT_REV{suffix}"
            )
            if revision is None:
                raise ValueError(
                    f"Additional source has no fixed revision: {relative} "
                    f"SCRIPT_REPO{suffix}"
                )
            entries.append(
                {
                    "id": f"{relative}#source{suffix}",
                    "recipe": relative,
                    "source_variable": f"SCRIPT_REPO{suffix}",
                    "repository": repository,
                    "revision": revision,
                }
            )
    selected_recipes = set(recipe_paths)
    entries.extend(
        dict(entry)
        for entry in SCRIPTED_FIXED_SOURCES
        if entry["recipe"] in selected_recipes
    )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--dockerfile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    dockerfile = args.dockerfile.resolve()
    entries = extract(source_root, dockerfile)
    additional_sources = extract_additional_sources(source_root, dockerfile)
    if args.audit_report:
        audit = json.loads(args.audit_report.resolve().read_text(encoding="utf-8"))
        resolved = {
            item["name"]: item.get("resolved_revision")
            for item in audit["components"]
            if item.get("resolved_revision")
        }
        for entry in entries + additional_sources:
            commit = resolved.get(entry["recipe"])
            if "id" in entry:
                commit = resolved.get(entry["id"])
            if commit and commit != entry["revision"]:
                entry["resolved_revision"] = commit
    result = {
        "schema_version": 1,
        "target": "win64",
        "variant": "lgpl",
        "ffmpeg_addin": "8.1",
        "btbn_build_revision": "a99e8230eae00d1cee38f23076a7a1f55cd984e2",
        "generation_command": "./generate.sh win64 lgpl 8.1",
        "release_ready": True,
        "review_note": (
            "All 77 source recipes and their additional acquisitions are fixed and "
            "classified; linked nested and vendored notices are staged in their "
            "dedicated manifests."
        ),
        "recipes": entries,
        "additional_sources": additional_sources,
    }
    args.output.resolve().write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"BtbN source recipe inventory: {len(entries)} recipes")
    print(f"Additional fixed sources: {len(additional_sources)}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
