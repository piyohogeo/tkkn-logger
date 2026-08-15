from __future__ import annotations

from pathlib import Path

import pytest

from tokkun99_logger.app_paths import AppPaths
from tokkun99_logger.config import LoggerConfig
from tokkun99_logger.data_layout import DataLayout


def test_logger_config_defaults_to_wgc_and_validates_values() -> None:
    config = LoggerConfig()

    assert config.capture_backend == "wgc"
    assert config.retention_mode == "records_only"
    assert config.duration_seconds is None
    assert config.minimum_free_bytes == 2 * 1024**3

    with pytest.raises(ValueError, match="fps"):
        LoggerConfig(fps=0)
    with pytest.raises(ValueError, match="sample_every"):
        LoggerConfig(sample_every=0)
    with pytest.raises(ValueError, match="non-negative"):
        LoggerConfig(message_hold_seconds=-1)


def test_data_layout_can_separate_templates_from_writable_data(tmp_path: Path) -> None:
    resources = tmp_path / "resources" / "template"
    writable = tmp_path / "portable-data"
    layout = DataLayout(writable, resources)

    assert layout.template == resources
    assert layout.state_profile == resources / "states" / "v1" / "profile.json"
    assert layout.database == writable / "log" / "logger.sqlite3"


def test_development_paths_preserve_existing_layout(tmp_path: Path) -> None:
    paths = AppPaths.for_development(tmp_path, ffmpeg_path=tmp_path / "ffmpeg.exe")

    assert paths.resource_root == tmp_path / "data" / "template"
    assert paths.data_root == tmp_path / "data"
    assert paths.layout.template == tmp_path / "data" / "template"
