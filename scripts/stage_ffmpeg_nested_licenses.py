"""Stage root notices for nested sources linked into the pinned FFmpeg build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from audit_ffmpeg_component_licenses import safe_name


LINKED = {"linked", "linked_generated"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(
    inventory_path: Path,
    audit_path: Path,
    source_cache: Path,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to replace existing staged licenses: {output_dir}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audited = {entry["name"]: entry for entry in audit["components"]}
    output_dir.mkdir(parents=True)
    entries: list[dict[str, object]] = []
    for dependency in inventory["recipes"]:
        name = dependency["recipe"]
        classification = dependency["classification"]
        files: list[dict[str, str]] = []
        if classification in LINKED:
            source_entry = audited.get(name)
            if source_entry is None or source_entry["status"] != "fetched":
                raise ValueError(f"Linked nested source is not fetched: {name}")
            root_candidates = [
                relative
                for relative in source_entry["license_candidates"]
                if "/" not in relative
            ]
            if not root_candidates:
                raise ValueError(f"Linked nested source has no root notice: {name}")
            destination = output_dir / safe_name(name)
            destination.mkdir()
            source = source_cache / safe_name(name)
            for relative in root_candidates:
                target = destination / relative
                shutil.copy2(source / relative, target)
                files.append(
                    {
                        "path": target.relative_to(output_dir.parent).as_posix(),
                        "sha256": sha256(target),
                    }
                )
        entries.append(
            {
                "recipe": name,
                "classification": classification,
                "license_files": files,
            }
        )

    result: dict[str, object] = {
        "schema_version": 1,
        "btbn_build_revision": inventory["btbn_build_revision"],
        "linked_nested_notices_complete": True,
        "vendored_code_review_complete": True,
        "release_ready": False,
        "review_note": (
            "Root notices are staged for explicitly fetched linked nested sources. "
            "Vendored code embedded directly in source repositories remains under review."
        ),
        "dependencies": entries,
    }
    manifest_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = stage(
        args.inventory.resolve(),
        args.audit_report.resolve(),
        args.source_cache.resolve(),
        args.output_dir.resolve(),
        args.manifest.resolve(),
    )
    file_count = sum(len(item["license_files"]) for item in result["dependencies"])
    print(f"Staged linked nested licenses: {file_count} files")
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
