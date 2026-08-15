"""Classify rav1e's Cargo graph and stage notices for distributable candidates."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


NOTICE_PREFIXES = ("license", "copying", "notice", "copyright", "patents")
LIBRARY_FEATURES = ("asm", "threading", "signal_support", "git_version", "capi")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_metadata(source: Path, target: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--locked",
            "--no-default-features",
            "--features",
            ",".join(LIBRARY_FEATURES),
            "--filter-platform",
            target,
            "--quiet",
        ],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def classify(metadata: dict[str, object]) -> dict[str, str]:
    resolve = metadata["resolve"]
    nodes = {node["id"]: node for node in resolve["nodes"]}
    packages = {package["id"]: package for package in metadata["packages"]}
    root = resolve["root"]
    states = {root: "linked_candidate"}
    queue = deque([root])

    while queue:
        package_id = queue.popleft()
        parent_state = states[package_id]
        for dependency in nodes[package_id]["deps"]:
            kinds = [
                item for item in dependency["dep_kinds"] if item["kind"] != "dev"
            ]
            if not kinds:
                continue
            child_id = dependency["pkg"]
            has_normal_edge = any(item["kind"] is None for item in kinds)
            next_state = (
                "linked_candidate"
                if parent_state == "linked_candidate" and has_normal_edge
                else "build_tool"
            )
            is_proc_macro = any(
                "proc-macro" in target["kind"]
                for target in packages[child_id]["targets"]
            )
            if is_proc_macro:
                next_state = "build_tool"

            previous = states.get(child_id)
            if previous is None or (
                previous == "build_tool" and next_state == "linked_candidate"
            ):
                states[child_id] = next_state
                queue.append(child_id)
    return states


def notice_sources(
    package: dict[str, object], overrides: dict[str, object], overrides_root: Path
) -> list[tuple[Path, str]]:
    root = Path(package["manifest_path"]).parent
    explicit = package.get("license_file")
    if explicit:
        path = root / explicit
        if not path.is_file():
            raise FileNotFoundError(f"Cargo license_file is missing: {path}")
        return [(path, "crate-package")]
    packaged = sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.name.lower().startswith(NOTICE_PREFIXES)
    )
    if packaged:
        return [(path, "crate-package") for path in packaged]

    key = f"{package['name']}@{package['version']}"
    override = overrides.get(key)
    if override is None:
        return []
    vcs_path = root / ".cargo_vcs_info.json"
    vcs = json.loads(vcs_path.read_text(encoding="utf-8"))
    if vcs["git"]["sha1"] != override["crate_vcs_revision"]:
        raise ValueError(f"Cargo override revision mismatch: {key}")
    result: list[tuple[Path, str]] = []
    for item in override["files"]:
        path = overrides_root / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Cargo override hash mismatch: {path}")
        result.append((path, item["url"]))
    return result


def stage(
    source: Path,
    expected_lock: Path,
    overrides_path: Path,
    output_dir: Path,
    manifest_path: Path,
    target: str,
) -> dict[str, object]:
    source_lock = source / "Cargo.lock"
    if source_lock.read_bytes() != expected_lock.read_bytes():
        raise ValueError(
            "Source Cargo.lock does not match the checked reconstruction: "
            f"{expected_lock}"
        )

    metadata = load_metadata(source, target)
    override_document = json.loads(overrides_path.read_text(encoding="utf-8"))
    overrides = override_document["packages"]
    states = classify(metadata)
    packages_by_id = {
        package["id"]: package for package in metadata["packages"]
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []

    for package_id, classification in sorted(
        states.items(), key=lambda item: (
            packages_by_id[item[0]]["name"],
            packages_by_id[item[0]]["version"],
        )
    ):
        package = packages_by_id[package_id]
        license_expression = package.get("license")
        if classification == "linked_candidate" and not license_expression:
            raise ValueError(
                f"Linked Cargo package lacks license metadata: {package['name']} "
                f"{package['version']}"
            )

        files: list[dict[str, str]] = []
        if classification == "linked_candidate":
            sources = notice_sources(package, overrides, overrides_path.parent)
            if not sources:
                raise FileNotFoundError(
                    f"Linked Cargo package has no notice file: {package['name']} "
                    f"{package['version']}"
                )
            destination = output_dir / f"{package['name']}-{package['version']}"
            destination.mkdir(exist_ok=True)
            for source_file, origin in sources:
                target_file = destination / source_file.name
                if target_file.exists():
                    if target_file.read_bytes() != source_file.read_bytes():
                        raise ValueError(
                            f"Existing staged Cargo notice differs: {target_file}"
                        )
                else:
                    shutil.copy2(source_file, target_file)
                files.append(
                    {
                        "path": target_file.relative_to(output_dir.parent).as_posix(),
                        "sha256": sha256(target_file),
                        "origin": origin,
                    }
                )

        entries.append(
            {
                "name": package["name"],
                "version": package["version"],
                "source": package.get("source") or "rav1e-workspace",
                "classification": classification,
                "license": license_expression,
                "license_files": files,
            }
        )

    toolchain_entries: list[dict[str, object]] = []
    for component in override_document.get("toolchain_components", []):
        directory_name = f"rust-std-{component['version']}"
        destination = output_dir / directory_name
        destination.mkdir(exist_ok=True)
        files: list[dict[str, str]] = []
        for item in component["files"]:
            source_file = overrides_path.parent / item["path"]
            if not source_file.is_file() or sha256(source_file) != item["sha256"]:
                raise ValueError(
                    f"Rust toolchain notice hash mismatch: {source_file}"
                )
            target_file = destination / source_file.name
            if target_file.exists():
                if target_file.read_bytes() != source_file.read_bytes():
                    raise ValueError(
                        f"Existing Rust toolchain notice differs: {target_file}"
                    )
            else:
                shutil.copy2(source_file, target_file)
            files.append(
                {
                    "path": target_file.relative_to(output_dir.parent).as_posix(),
                    "sha256": sha256(target_file),
                    "origin": item["origin"],
                }
            )
        entry = {key: value for key, value in component.items() if key != "files"}
        entry["license_files"] = files
        toolchain_entries.append(entry)

    expected_directories = {
        f"{item['name']}-{item['version']}"
        for item in entries
        if item["classification"] == "linked_candidate"
    }
    expected_directories.update(
        f"rust-std-{item['version']}" for item in toolchain_entries
    )
    actual_directories = {path.name for path in output_dir.iterdir() if path.is_dir()}
    stale_directories = sorted(actual_directories - expected_directories)
    if stale_directories:
        raise ValueError(
            "Stale rav1e Cargo notice directories are present: "
            + ", ".join(stale_directories)
        )

    result: dict[str, object] = {
        "schema_version": 1,
        "btbn_build_revision": "a99e8230eae00d1cee38f23076a7a1f55cd984e2",
        "rav1e_revision": "564ae3b0007ae2b06893fd7166bf88c5a84c5b63",
        "target": target,
        "cargo_features": list(LIBRARY_FEATURES),
        "excluded_default_feature": "binaries",
        "cargo_c_cfg": True,
        "reconstructed_cc_version": "1.4.0",
        "source_lock_sha256": sha256(expected_lock),
        "linked_candidate_count": sum(
            item["classification"] == "linked_candidate" for item in entries
        ),
        "build_tool_count": sum(
            item["classification"] == "build_tool" for item in entries
        ),
        "notices_complete_for_reconstructed_graph": True,
        "toolchain_notices_complete": bool(toolchain_entries),
        "rust_toolchain_binary_attested": True,
        "actual_build_lock_attested": False,
        "unattested_build_risk_acceptance": {
            "accepted": True,
            "accepted_by": "project_owner",
            "recorded_on": "2026-08-16",
            "scope": (
                "Accept the reconstructed rav1e Cargo graph and unpinned cargo-c "
                "version as a documented v0.1.0 release limitation."
            ),
        },
        "release_ready": True,
        "review_note": (
            "The distributed ffmpeg.exe attests Rust 1.97.1 commit 8bab26f and "
            "contains standard-library dependency paths covered by the staged "
            "official rustc notices. The public BtbN Actions log expired, so the "
            "rav1e Cargo graph still reconstructs the 2026-07-31 cargo update "
            "from the publish timeline; it is not an archived attestation of the "
            "actual Cargo build lockfile."
        ),
        "packages": entries,
        "toolchain_components": toolchain_entries,
    }
    with manifest_path.open("w", encoding="utf-8", newline="\n") as manifest_file:
        manifest_file.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-lock", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", default="x86_64-pc-windows-gnu")
    args = parser.parse_args()
    result = stage(
        args.source.resolve(),
        args.expected_lock.resolve(),
        args.overrides.resolve(),
        args.output_dir.resolve(),
        args.manifest.resolve(),
        args.target,
    )
    file_count = sum(len(item["license_files"]) for item in result["packages"])
    file_count += sum(
        len(item["license_files"])
        for item in result["toolchain_components"]
    )
    print(
        f"Staged rav1e Cargo notices: {file_count} files for "
        f"{result['linked_candidate_count']} linked candidates"
    )
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
