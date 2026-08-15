"""Fetch fixed FFmpeg component sources and inventory their license files.

The resulting report is evidence for manual license review. It does not mark a
component release-ready or copy unreviewed files into a distribution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


LICENSE_NAME = re.compile(
    r"^(?:copying|copyright|license|licence|notice|patents?)"
    r"(?:[.-](?!check(?:er)?(?:[.-]|$)).*)?$",
    re.IGNORECASE,
)


def safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    if not value:
        raise ValueError(f"Component name has no safe path representation: {name!r}")
    return value


def run_git(*arguments: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=180,
    )
    return completed.stdout


def optional_git(*arguments: str, cwd: Path) -> str:
    try:
        return run_git(*arguments, cwd=cwd).strip()
    except subprocess.CalledProcessError:
        return ""


def fetch_revision(destination: Path, repository: str, revision: str) -> str:
    if destination.exists():
        if not (destination / ".git").is_dir():
            raise ValueError(f"Existing component cache is not a Git repository: {destination}")
        current = optional_git("rev-parse", "HEAD", cwd=destination)
        requested = optional_git("config", "--get", "ffmpegAudit.requestedRevision", cwd=destination)
        if current == revision or (current and requested == revision):
            return current
    else:
        destination.mkdir(parents=True)
        run_git("init", "--quiet", cwd=destination)
        run_git("remote", "add", "origin", repository, cwd=destination)
    run_git("fetch", "--quiet", "--depth", "1", "origin", revision, cwd=destination)
    run_git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=destination)
    current = run_git("rev-parse", "HEAD", cwd=destination).strip()
    if re.fullmatch(r"[0-9a-f]{40}", revision) and current != revision:
        raise ValueError(f"Fetched revision mismatch: {current} != {revision}")
    run_git("config", "ffmpegAudit.requestedRevision", revision, cwd=destination)
    return current


def license_candidates(source: Path) -> list[str]:
    tracked = run_git("ls-files", cwd=source).splitlines()
    candidates = [
        path
        for path in tracked
        if LICENSE_NAME.fullmatch(Path(path).name) is not None
    ]
    return sorted(candidates, key=lambda value: (len(Path(value).parts), value.casefold()))


def submodules(source: Path) -> list[dict[str, str]]:
    gitmodules = source / ".gitmodules"
    if not gitmodules.is_file():
        return []
    try:
        paths = run_git(
            "config",
            "--file",
            ".gitmodules",
            "--get-regexp",
            r"^submodule\..*\.path$",
            cwd=source,
        ).splitlines()
    except subprocess.CalledProcessError:
        return []
    result: list[dict[str, str]] = []
    for line in paths:
        key, path = line.split(maxsplit=1)
        section = key[: -len(".path")]
        url = run_git("config", "--file", ".gitmodules", "--get", f"{section}.url", cwd=source).strip()
        try:
            revision = run_git("ls-tree", "HEAD", path, cwd=source).split()[2]
        except (IndexError, subprocess.CalledProcessError):
            revision = ""
        result.append({"path": path, "repository": url, "revision": revision})
    return result


def audit(manifest: Path, cache: Path, report: Path, fetch: bool) -> dict[str, object]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if "components" in data:
        records = [
            {
                "name": component["name"],
                "repository": component["source_repository"],
                "revision": component["revision"],
            }
            for component in data["components"]
        ]
    elif "recipes" in data:
        records = [
            {
                "name": recipe["recipe"],
                "repository": recipe["repository"],
                "revision": recipe["revision"],
            }
            for recipe in data["recipes"]
        ]
        records.extend(
            {
                "name": source["id"],
                "repository": source["repository"],
                "revision": source["revision"],
            }
            for source in data.get("additional_sources", [])
        )
    else:
        raise ValueError("Manifest must contain components or recipes")
    cache.mkdir(parents=True, exist_ok=True)
    audited: list[dict[str, object]] = []
    for component in records:
        name = str(component["name"])
        repository = str(component["repository"])
        revision = str(component["revision"])
        source = cache / safe_name(name)
        entry: dict[str, object] = {
            "name": name,
            "repository": repository,
            "revision": revision,
            "resolved_revision": None,
            "status": "not_fetched",
            "license_candidates": [],
            "submodules": [],
        }
        git_revision = re.fullmatch(r"[0-9a-f]{40}", revision) is not None or re.fullmatch(
            r"(?:v?\d[0-9A-Za-z._-]*|openssl-[0-9A-Za-z._-]+)", revision
        ) is not None
        if repository.startswith("https://svn.") or not git_revision:
            entry["status"] = "manual_review"
        elif fetch:
            try:
                entry["resolved_revision"] = fetch_revision(source, repository, revision)
                entry["license_candidates"] = license_candidates(source)
                entry["submodules"] = submodules(source)
                entry["status"] = "fetched"
            except (
                OSError,
                ValueError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ) as error:
                entry["status"] = "fetch_failed"
                entry["error"] = str(error)
        audited.append(entry)

    result: dict[str, object] = {
        "schema_version": 1,
        "source_manifest": str(manifest),
        "review_warning": (
            "Candidate discovery is not legal review. Nested vendored code and submodules "
            "must be reviewed before notice files are approved."
        ),
        "components": audited,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path("packaging/ffmpeg-components.json")
    )
    parser.add_argument(
        "--cache", type=Path, default=Path("build/ffmpeg-component-sources")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("build/ffmpeg-component-license-audit.json")
    )
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()

    result = audit(
        args.manifest.resolve(), args.cache.resolve(), args.report.resolve(), args.fetch
    )
    statuses: dict[str, int] = {}
    for component in result["components"]:
        status = str(component["status"])
        statuses[status] = statuses.get(status, 0) + 1
    print("FFmpeg component license audit: " + ", ".join(f"{k}={v}" for k, v in statuses.items()))
    print(f"Report: {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
