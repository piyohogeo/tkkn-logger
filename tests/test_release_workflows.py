from __future__ import annotations

from pathlib import Path
import re


PROJECT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> str:
    return (PROJECT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_all_github_actions_are_pinned_to_full_commit_shas() -> None:
    uses_lines = re.findall(r"^\s*uses:\s*(\S+)", workflow("ci.yml") + workflow("release.yml"), re.MULTILINE)

    assert uses_lines
    assert all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", value) for value in uses_lines)


def test_ci_never_creates_a_release() -> None:
    ci = workflow("ci.yml")

    assert "pull_request:" in ci
    assert "workflow_dispatch:" in ci
    assert "contents: read" in ci
    assert "gh release" not in ci
    assert "tags:" not in ci


def test_release_workflow_only_grants_write_to_draft_job() -> None:
    release = workflow("release.yml")

    assert '      - "v*"' in release
    assert "if: github.ref_type == 'tag'" in release
    assert release.count("contents: write") == 1
    assert "gh release create $tag" in release
    assert "--draft" in release
    assert "--verify-tag" in release
    assert "<full-commit-sha>" in release
