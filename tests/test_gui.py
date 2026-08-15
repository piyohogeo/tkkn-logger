from __future__ import annotations

import pytest

from tokkun99_logger.app_paths import AppPaths
from tokkun99_logger.gui import GuiState, apply_event, ensure_data_directory
from tokkun99_logger.logger_events import LoggerEvent


def test_gui_state_tracks_service_recording_and_error_events() -> None:
    state = apply_event(GuiState(), LoggerEvent("service_starting", "starting"))
    state = apply_event(
        state, LoggerEvent("target_found", "found", data={"target_size": (320, 240)})
    )
    state = apply_event(state, LoggerEvent("recording_started", "recording"))
    state = apply_event(
        state,
        LoggerEvent(
            "service_status",
            "PLAYING",
            data={
                "game_state": "PLAYING",
                "recording": True,
                "recording_paused": False,
                "recording_seconds": 12.5,
            },
        ),
    )

    assert state.game_detection == "検出済み / 320x240"
    assert state.game_state == "PLAYING"
    assert state.recording_state == "録画中"
    assert state.recording_seconds == 12.5

    state = apply_event(state, LoggerEvent("recording_finished", "done"))
    assert state.recording_state == "待機"
    assert state.recording_seconds == 0.0

    state = apply_event(state, LoggerEvent("error", "capture failed"))
    assert state.service_state == "エラー"
    assert state.last_error == "capture failed"


def test_data_folder_action_resolves_only_configured_data_root(tmp_path) -> None:
    paths = AppPaths(tmp_path / "elsewhere" / "template", tmp_path / "chosen-data")

    assert ensure_data_directory(paths) == (tmp_path / "chosen-data").resolve()
    assert (tmp_path / "chosen-data").is_dir()


def test_tk_gui_can_be_constructed_and_destroyed_when_display_is_available(tmp_path) -> None:
    import tkinter as tk

    from tokkun99_logger.app_paths import AppPaths
    from tokkun99_logger.gui import LoggerGui

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        LoggerGui(root, AppPaths(tmp_path / "template", tmp_path / "data", tmp_path / "ffmpeg"))
        root.update_idletasks()
    finally:
        root.destroy()
