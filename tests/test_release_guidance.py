from __future__ import annotations

from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
GAME_DOWNLOAD_URL = "https://bee.in.coocan.jp/tk"
OFFICIAL_SITE_URL = "https://bee.in.coocan.jp/"


def guidance(path: str) -> str:
    return (PROJECT / path).read_text(encoding="utf-8")


def test_release_notes_identify_game_and_both_record_types() -> None:
    notes = guidance("packaging/RELEASE_NOTES_v0.1.0.md")

    assert GAME_DOWNLOAD_URL in notes
    assert OFFICIAL_SITE_URL in notes
    assert "作者のびい氏に感謝" in notes
    assert "ゲーム本体はこのロガーのReleaseに含まれません" in notes
    assert "生存時間の歴代記録を更新したrunの動画" in notes
    assert "RESULT画面に表示される弾数の歴代記録を更新したrunの動画" in notes


def test_portable_readme_keeps_game_guidance_and_record_policy() -> None:
    readme = guidance("packaging/README_PORTABLE.txt")

    assert GAME_DOWNLOAD_URL in readme
    assert OFFICIAL_SITE_URL in readme
    assert "作者のびい氏に感謝" in readme
    assert "ゲーム本体はこの配布物に含まれません" in readme
    assert "生存時間記録" in readme
    assert "弾数記録" in readme
    assert "どちらか一方でも以前の最大値を\n上回ったrunの動画を保持" in readme
    assert "同値は新記録として扱いません" in readme


def test_portable_builder_copies_guidance_to_readme_txt() -> None:
    builder = guidance("scripts/build_portable.ps1")

    assert '"packaging\\README_PORTABLE.txt"' in builder
    assert '-Destination (Join-Path $appRoot "README.txt")' in builder
