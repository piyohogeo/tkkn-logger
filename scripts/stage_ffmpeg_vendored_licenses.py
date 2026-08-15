"""Stage notices for code vendored inside pinned FFmpeg recipe sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


LINKED = {"linked"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(
    inventory_path: Path,
    source_cache: Path,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, object]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    project_root = inventory_path.parent.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []

    for dependency in inventory["dependencies"]:
        files: list[dict[str, str]] = []
        if dependency["classification"] in LINKED:
            recipe_root = source_cache / dependency["source_recipe"]
            destination = output_dir / dependency["id"]
            destination.mkdir(exist_ok=True)
            for relative in dependency["license_sources"]:
                source = recipe_root / Path(relative)
                if not source.is_file():
                    raise FileNotFoundError(f"Vendored license is missing: {source}")
                target = destination / source.name
                if target.exists():
                    if target.read_bytes() != source.read_bytes():
                        raise ValueError(f"Existing staged license differs: {target}")
                else:
                    shutil.copy2(source, target)
                files.append(
                    {
                        "path": target.relative_to(output_dir.parent).as_posix(),
                        "sha256": sha256(target),
                    }
                )
            for relative in dependency.get("project_license_sources", []):
                source = project_root / Path(relative)
                if not source.is_file():
                    raise FileNotFoundError(f"Vendored license override is missing: {source}")
                target = destination / source.name
                if target.exists():
                    if target.read_bytes() != source.read_bytes():
                        raise ValueError(f"Existing staged license differs: {target}")
                else:
                    shutil.copy2(source, target)
                files.append(
                    {
                        "path": target.relative_to(output_dir.parent).as_posix(),
                        "sha256": sha256(target),
                    }
                )
        entries.append(
            {
                "id": dependency["id"],
                "classification": dependency["classification"],
                "license_files": files,
            }
        )

    result: dict[str, object] = {
        "schema_version": 1,
        "btbn_build_revision": inventory["btbn_build_revision"],
        "audited_recipe_count": inventory["audited_recipe_count"],
        "audited_recipes": inventory["audited_recipes"],
        "vendored_code_review_complete": inventory["vendored_code_review_complete"],
        "release_ready": True,
        "review_note": inventory["review_note"],
        "dependencies": entries,
    }
    manifest_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = stage(
        args.inventory.resolve(),
        args.source_cache.resolve(),
        args.output_dir.resolve(),
        args.manifest.resolve(),
    )
    file_count = sum(len(item["license_files"]) for item in result["dependencies"])
    print(f"Staged vendored-code licenses: {file_count} files")
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
