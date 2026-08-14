from __future__ import annotations

from pathlib import Path

from tokkun99_logger.data_layout import DataLayout


def test_data_layout_separates_collection_log_and_template(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path / "data")

    assert layout.messages == tmp_path / "data" / "collection" / "messages"
    assert layout.videos == tmp_path / "data" / "collection" / "videos"
    assert layout.runs == tmp_path / "data" / "collection" / "runs"
    assert layout.database == tmp_path / "data" / "log" / "logger.sqlite3"
    assert layout.message_log == tmp_path / "data" / "log" / "messages"
    assert layout.template == tmp_path / "data" / "template"
