from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.collect_portable_licenses import verify_rav1e_cargo_license_bundle


PROJECT = Path(__file__).resolve().parents[1]


def test_rav1e_reconstructed_graph_is_complete_but_unattested() -> None:
    manifest = json.loads(
        (PROJECT / "packaging" / "rav1e-cargo-licenses.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["target"] == "x86_64-pc-windows-gnu"
    assert manifest["reconstructed_cc_version"] == "1.4.0"
    assert manifest["linked_candidate_count"] == 42
    assert manifest["build_tool_count"] == 55
    assert manifest["notices_complete_for_reconstructed_graph"] is True
    assert manifest["toolchain_notices_complete"] is True
    assert manifest["rust_toolchain_binary_attested"] is True
    assert manifest["actual_build_lock_attested"] is False
    assert manifest["release_ready"] is False
    assert len(manifest["packages"]) == 97
    toolchain = manifest["toolchain_components"]
    assert len(toolchain) == 1
    assert toolchain[0]["version"] == "1.97.1"
    assert (
        toolchain[0]["rustc_commit"]
        == "8bab26f4f68e0e26f0bb7960be334d5b520ea452"
    )
    assert {"addr2line-0.25.1", "gimli-0.32.3", "object-0.37.3"}.issubset(
        toolchain[0]["binary_evidence"]
    )
    assert not [
        package
        for package in manifest["packages"]
        if package["classification"] == "linked_candidate" and not package["license"]
    ]


def test_rav1e_lock_and_notice_hashes_match() -> None:
    manifest = json.loads(
        (PROJECT / "packaging" / "rav1e-cargo-licenses.json").read_text(
            encoding="utf-8"
        )
    )
    lock = PROJECT / "packaging" / "rav1e-Cargo.lock"
    assert hashlib.sha256(lock.read_bytes()).hexdigest() == manifest["source_lock_sha256"]
    verify_rav1e_cargo_license_bundle(
        manifest, PROJECT / "packaging" / "rav1e-cargo-licenses"
    )


def test_rav1e_upstream_license_override_is_fixed_and_hashed() -> None:
    document = json.loads(
        (
            PROJECT / "packaging" / "rav1e-cargo-license-overrides.json"
        ).read_text(encoding="utf-8")
    )
    override = document["packages"]["profiling@1.0.16"]
    assert override["crate_vcs_revision"] == "0ba524064aae5b4972e6be3424a2acb316f93ba3"
    for item in override["files"]:
        path = PROJECT / "packaging" / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    toolchain = document["toolchain_components"][0]
    assert (
        toolchain["distribution_sha256"]
        == "11de14fa7ee410e9baaa070ce0cda44e155c0e9e32329db0b5f20efc0f2fa5e4"
    )
    for item in toolchain["files"]:
        path = PROJECT / "packaging" / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
