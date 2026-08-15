"""Collect license files for software included in the portable build."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess


DISTRIBUTIONS = (
    "numpy",
    "opencv-python",
    "mss",
    "windows-capture",
    "pywin32",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
)
LICENSE_MARKERS = ("license", "licence", "copying", "notice")
FFMPEG_LICENSE_OUTPUT = "FFmpeg-LGPL-3.0-or-later.txt"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_recipe_license_bundle(manifest: dict[str, object], root: Path) -> None:
    prefix = "ffmpeg-recipe-licenses/"
    if manifest["recipe_root_notices_complete"] is not True:
        raise ValueError("FFmpeg recipe root notices are incomplete")
    for recipe in manifest["recipes"]:
        for item in recipe["license_files"]:
            relative = str(item["path"])
            if not relative.startswith(prefix) or ".." in Path(relative).parts:
                raise ValueError(f"Unsafe FFmpeg recipe license path: {relative}")
            source = root / relative[len(prefix) :]
            if not source.is_file() or file_sha256(source) != item["sha256"]:
                raise ValueError(f"FFmpeg recipe license hash mismatch: {relative}")


def verify_nested_license_bundle(manifest: dict[str, object], root: Path) -> None:
    prefix = "ffmpeg-nested-licenses/"
    if manifest["linked_nested_notices_complete"] is not True:
        raise ValueError("Linked FFmpeg nested notices are incomplete")
    for dependency in manifest["dependencies"]:
        files = dependency["license_files"]
        linked = dependency["classification"] in {"linked", "linked_generated"}
        if linked != bool(files):
            raise ValueError(
                f"Nested FFmpeg notice classification mismatch: {dependency['recipe']}"
            )
        for item in files:
            relative = str(item["path"])
            if not relative.startswith(prefix) or ".." in Path(relative).parts:
                raise ValueError(f"Unsafe FFmpeg nested license path: {relative}")
            source = root / relative[len(prefix) :]
            if not source.is_file() or file_sha256(source) != item["sha256"]:
                raise ValueError(f"FFmpeg nested license hash mismatch: {relative}")


def verify_vendored_license_bundle(manifest: dict[str, object], root: Path) -> None:
    prefix = "ffmpeg-vendored-licenses/"
    for dependency in manifest["dependencies"]:
        files = dependency["license_files"]
        linked = dependency["classification"] == "linked"
        if linked != bool(files):
            raise ValueError(
                f"Vendored FFmpeg notice classification mismatch: {dependency['id']}"
            )
        for item in files:
            relative = str(item["path"])
            if not relative.startswith(prefix) or ".." in Path(relative).parts:
                raise ValueError(f"Unsafe FFmpeg vendored license path: {relative}")
            source = root / relative[len(prefix) :]
            if not source.is_file() or file_sha256(source) != item["sha256"]:
                raise ValueError(f"FFmpeg vendored license hash mismatch: {relative}")


def verify_rav1e_cargo_license_bundle(
    manifest: dict[str, object], root: Path
) -> None:
    prefix = "rav1e-cargo-licenses/"
    for package in manifest["packages"]:
        files = package["license_files"]
        linked = package["classification"] == "linked_candidate"
        if linked != bool(files):
            raise ValueError(
                f"rav1e Cargo notice classification mismatch: {package['name']}"
            )
        for item in files:
            relative = str(item["path"])
            if not relative.startswith(prefix) or ".." in Path(relative).parts:
                raise ValueError(f"Unsafe rav1e Cargo license path: {relative}")
            source = root / relative[len(prefix) :]
            if not source.is_file() or file_sha256(source) != item["sha256"]:
                raise ValueError(f"rav1e Cargo license hash mismatch: {relative}")
    toolchain_components = manifest.get("toolchain_components", [])
    if manifest.get("toolchain_notices_complete") is not True or not toolchain_components:
        raise ValueError("rav1e Rust toolchain notices are incomplete")
    for component in toolchain_components:
        files = component["license_files"]
        if not files:
            raise ValueError(
                f"rav1e Rust toolchain notice is missing: {component['name']}"
            )
        for item in files:
            relative = str(item["path"])
            if not relative.startswith(prefix) or ".." in Path(relative).parts:
                raise ValueError(f"Unsafe rav1e toolchain license path: {relative}")
            source = root / relative[len(prefix) :]
            if not source.is_file() or file_sha256(source) != item["sha256"]:
                raise ValueError(f"rav1e toolchain license hash mismatch: {relative}")


def is_license_file(relative: str) -> bool:
    name = Path(relative).name.casefold()
    return any(marker in name for marker in LICENSE_MARKERS) and not name.endswith(".xml")


def collect_distribution_licenses(output: Path) -> list[str]:
    copied: list[str] = []
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        dependency_dir = output / f"{name}-{distribution.version}"
        for relative in distribution.files or ():
            relative_text = str(relative)
            if not is_license_file(relative_text):
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file():
                continue
            safe_parts = [
                part.replace(":", "_")
                for part in Path(relative_text).parts
                if part not in (".", "..")
            ]
            target = dependency_dir.joinpath(*safe_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(output).as_posix())
    return copied


def capture_ffmpeg_build_info(ffmpeg: Path, ffmpeg_manifest: dict[str, str]) -> str:
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return "\n".join(
        [
            f"Provider: {ffmpeg_manifest['provider']}",
            f"Version: {ffmpeg_manifest['version']}",
            f"Variant: {ffmpeg_manifest['variant']}",
            f"Archive: {ffmpeg_manifest['archive_url']}",
            f"FFmpeg source: {ffmpeg_manifest['ffmpeg_source_url']}",
            f"Build source: {ffmpeg_manifest['build_source_url']}",
            f"ffmpeg.exe SHA-256: {ffmpeg_manifest['ffmpeg_sha256']}",
            "",
            "ffmpeg.exe -hide_banner -version:",
            (completed.stdout + completed.stderr).strip(),
            "",
        ]
    )


def write_notices(
    output: Path,
    ffmpeg_manifest: dict[str, str],
    ffmpeg_components: dict[str, object],
    ffmpeg_recipes: dict[str, object],
    ffmpeg_recipe_licenses: dict[str, object],
    ffmpeg_nested_licenses: dict[str, object],
    ffmpeg_vendored_licenses: dict[str, object],
    ffmpeg_additional_sources: dict[str, object],
    rav1e_cargo_licenses: dict[str, object],
) -> None:
    lines = [
        "Tokkun '99 Logger - Third-party software notices",
        "",
        "The portable directory includes the following third-party software.",
        "Full license texts are stored below this directory.",
        "",
    ]
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        home = distribution.metadata.get("Home-page") or "(see package metadata)"
        lines.append(f"- {name} {distribution.version}: {home}")
    lines.extend(
        [
            f"- FFmpeg {ffmpeg_manifest['version']} ({ffmpeg_manifest['variant']})",
            f"  Provider: {ffmpeg_manifest['provider']}",
            f"  License: {ffmpeg_manifest['license']}",
            f"  FFmpeg source: {ffmpeg_manifest['ffmpeg_source_url']}",
            f"  Build source: {ffmpeg_manifest['build_source_url']}",
            f"  ffmpeg.exe SHA-256: {ffmpeg_manifest['ffmpeg_sha256']}",
            "  FFmpeg runs as a separate process and is not linked into this application.",
            "  See FFmpeg-BUILD.txt and FFmpeg-MANIFEST.json for reproducible build details.",
            f"  External component audit release-ready: {ffmpeg_components['release_ready']}",
            f"  Build recipe audit release-ready: {ffmpeg_recipes['release_ready']}",
            "  Recipe root notices complete: "
            f"{ffmpeg_recipe_licenses['recipe_root_notices_complete']}",
            "  Nested dependency review complete: "
            f"{ffmpeg_recipe_licenses['nested_dependency_review_complete']}",
            "  Explicit linked nested notices complete: "
            f"{ffmpeg_nested_licenses['linked_nested_notices_complete']}",
            "  Vendored code review complete: "
            f"{ffmpeg_vendored_licenses['vendored_code_review_complete']}",
            "  Multi-source recipe classification complete: "
            f"{ffmpeg_additional_sources['review_complete']}",
            "  rav1e reconstructed Cargo notices complete: "
            f"{rav1e_cargo_licenses['notices_complete_for_reconstructed_graph']}",
            "  rav1e actual build lock attested: "
            f"{rav1e_cargo_licenses['actual_build_lock_attested']}",
            "  See FFmpeg-COMPONENTS.json and FFmpeg-BUILD-RECIPES.json for fixed revisions",
            "  and unresolved notice files, including transitive build dependencies.",
        ]
    )
    (output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg-root", type=Path, required=True)
    parser.add_argument("--ffmpeg-manifest", type=Path, required=True)
    parser.add_argument("--ffmpeg-components", type=Path, required=True)
    parser.add_argument("--ffmpeg-recipes", type=Path, required=True)
    parser.add_argument("--ffmpeg-recipe-licenses", type=Path, required=True)
    parser.add_argument("--ffmpeg-recipe-license-root", type=Path, required=True)
    parser.add_argument("--ffmpeg-nested-licenses", type=Path, required=True)
    parser.add_argument("--ffmpeg-nested-license-root", type=Path, required=True)
    parser.add_argument("--ffmpeg-nested-dependencies", type=Path, required=True)
    parser.add_argument("--ffmpeg-vendored-licenses", type=Path, required=True)
    parser.add_argument("--ffmpeg-vendored-license-root", type=Path, required=True)
    parser.add_argument("--ffmpeg-vendored-code", type=Path, required=True)
    parser.add_argument("--ffmpeg-additional-sources", type=Path, required=True)
    parser.add_argument("--rav1e-cargo-licenses", type=Path, required=True)
    parser.add_argument("--rav1e-cargo-license-root", type=Path, required=True)
    parser.add_argument("--rav1e-cargo-lock", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    ffmpeg_root = args.ffmpeg_root.resolve()
    ffmpeg_manifest_path = args.ffmpeg_manifest.resolve()
    ffmpeg_components_path = args.ffmpeg_components.resolve()
    ffmpeg_recipes_path = args.ffmpeg_recipes.resolve()
    ffmpeg_recipe_licenses_path = args.ffmpeg_recipe_licenses.resolve()
    ffmpeg_recipe_license_root = args.ffmpeg_recipe_license_root.resolve()
    ffmpeg_nested_licenses_path = args.ffmpeg_nested_licenses.resolve()
    ffmpeg_nested_license_root = args.ffmpeg_nested_license_root.resolve()
    ffmpeg_nested_dependencies_path = args.ffmpeg_nested_dependencies.resolve()
    ffmpeg_vendored_licenses_path = args.ffmpeg_vendored_licenses.resolve()
    ffmpeg_vendored_license_root = args.ffmpeg_vendored_license_root.resolve()
    ffmpeg_vendored_code_path = args.ffmpeg_vendored_code.resolve()
    ffmpeg_additional_sources_path = args.ffmpeg_additional_sources.resolve()
    rav1e_cargo_licenses_path = args.rav1e_cargo_licenses.resolve()
    rav1e_cargo_license_root = args.rav1e_cargo_license_root.resolve()
    rav1e_cargo_lock_path = args.rav1e_cargo_lock.resolve()
    ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
    ffmpeg_components = json.loads(ffmpeg_components_path.read_text(encoding="utf-8"))
    ffmpeg_recipes = json.loads(ffmpeg_recipes_path.read_text(encoding="utf-8"))
    ffmpeg_recipe_licenses = json.loads(
        ffmpeg_recipe_licenses_path.read_text(encoding="utf-8")
    )
    verify_recipe_license_bundle(ffmpeg_recipe_licenses, ffmpeg_recipe_license_root)
    ffmpeg_nested_licenses = json.loads(
        ffmpeg_nested_licenses_path.read_text(encoding="utf-8")
    )
    verify_nested_license_bundle(ffmpeg_nested_licenses, ffmpeg_nested_license_root)
    ffmpeg_vendored_licenses = json.loads(
        ffmpeg_vendored_licenses_path.read_text(encoding="utf-8")
    )
    verify_vendored_license_bundle(
        ffmpeg_vendored_licenses, ffmpeg_vendored_license_root
    )
    ffmpeg_additional_sources = json.loads(
        ffmpeg_additional_sources_path.read_text(encoding="utf-8")
    )
    if ffmpeg_additional_sources["review_complete"] is not True:
        raise ValueError("FFmpeg multi-source recipe classification is incomplete")
    rav1e_cargo_licenses = json.loads(
        rav1e_cargo_licenses_path.read_text(encoding="utf-8")
    )
    verify_rav1e_cargo_license_bundle(
        rav1e_cargo_licenses, rav1e_cargo_license_root
    )
    if file_sha256(rav1e_cargo_lock_path) != rav1e_cargo_licenses["source_lock_sha256"]:
        raise ValueError("rav1e reconstructed Cargo.lock hash mismatch")
    ffmpeg = ffmpeg_root / "bin" / "ffmpeg.exe"
    ffmpeg_license = ffmpeg_root / ffmpeg_manifest["license_file"]
    if not ffmpeg.is_file() or not ffmpeg_license.is_file():
        raise FileNotFoundError("Verified FFmpeg executable and license are required")

    output.mkdir(parents=True, exist_ok=True)
    collect_distribution_licenses(output)
    shutil.copy2(ffmpeg_license, output / FFMPEG_LICENSE_OUTPUT)
    (output / "FFmpeg-BUILD.txt").write_text(
        capture_ffmpeg_build_info(ffmpeg, ffmpeg_manifest), encoding="utf-8"
    )
    shutil.copy2(ffmpeg_manifest_path, output / "FFmpeg-MANIFEST.json")
    shutil.copy2(ffmpeg_components_path, output / "FFmpeg-COMPONENTS.json")
    shutil.copy2(ffmpeg_recipes_path, output / "FFmpeg-BUILD-RECIPES.json")
    shutil.copy2(
        ffmpeg_recipe_licenses_path, output / "FFmpeg-RECIPE-LICENSES.json"
    )
    shutil.copytree(
        ffmpeg_recipe_license_root,
        output / "ffmpeg-recipe-licenses",
        dirs_exist_ok=True,
    )
    shutil.copy2(ffmpeg_nested_licenses_path, output / "FFmpeg-NESTED-LICENSES.json")
    shutil.copy2(
        ffmpeg_nested_dependencies_path,
        output / "FFmpeg-NESTED-DEPENDENCIES.json",
    )
    shutil.copytree(
        ffmpeg_nested_license_root,
        output / "ffmpeg-nested-licenses",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        ffmpeg_vendored_licenses_path, output / "FFmpeg-VENDORED-LICENSES.json"
    )
    shutil.copy2(ffmpeg_vendored_code_path, output / "FFmpeg-VENDORED-CODE.json")
    shutil.copy2(
        ffmpeg_additional_sources_path,
        output / "FFmpeg-ADDITIONAL-SOURCES.json",
    )
    shutil.copytree(
        ffmpeg_vendored_license_root,
        output / "ffmpeg-vendored-licenses",
        dirs_exist_ok=True,
    )
    shutil.copy2(rav1e_cargo_licenses_path, output / "RAV1E-CARGO-LICENSES.json")
    shutil.copy2(rav1e_cargo_lock_path, output / "RAV1E-Cargo.lock")
    shutil.copytree(
        rav1e_cargo_license_root,
        output / "rav1e-cargo-licenses",
        dirs_exist_ok=True,
    )
    write_notices(
        output,
        ffmpeg_manifest,
        ffmpeg_components,
        ffmpeg_recipes,
        ffmpeg_recipe_licenses,
        ffmpeg_nested_licenses,
        ffmpeg_vendored_licenses,
        ffmpeg_additional_sources,
        rav1e_cargo_licenses,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
