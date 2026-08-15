from __future__ import annotations

from scripts.probe_capture import frame_stats, save_ppm
from tokkun99_logger.capture import (
    TargetWindow,
    resolve_client_crop,
    select_capturable_windows,
)


def test_resolve_client_crop_accepts_client_only_wgc_frame() -> None:
    window = TargetWindow(
        hwnd=1,
        pid=2,
        process_path=r"C:\Games\TKKN.EXE",
        title="game",
        visible=True,
        minimized=False,
        window_rect=(100, 100, 422, 367),
        client_origin=(101, 126),
        client_size=(320, 240),
        dpi=96,
    )

    assert resolve_client_crop((320, 240), window) == (0, 0, 320, 240)


def test_resolve_client_crop_removes_window_chrome(monkeypatch) -> None:
    window = TargetWindow(
        hwnd=1,
        pid=2,
        process_path=r"C:\Games\TKKN.EXE",
        title="game",
        visible=True,
        minimized=False,
        window_rect=(100, 100, 422, 367),
        client_origin=(101, 126),
        client_size=(320, 240),
        dpi=96,
    )
    monkeypatch.setattr("tokkun99_logger.capture.extended_frame_bounds", lambda _hwnd: None)

    assert resolve_client_crop((322, 267), window) == (1, 26, 321, 266)


def test_frame_stats_for_black_frame() -> None:
    frame = bytes([0, 0, 0, 255]) * 16

    black_fraction, brightness = frame_stats(frame)

    assert black_fraction == 1.0
    assert brightness == 0.0


def test_frame_stats_for_white_frame() -> None:
    frame = bytes([255, 255, 255, 255]) * 16

    black_fraction, brightness = frame_stats(frame)

    assert black_fraction == 0.0
    assert brightness == 255.0


def test_save_ppm_converts_bgra_to_rgb(tmp_path) -> None:
    output = tmp_path / "pixel.ppm"

    save_ppm(output, bytes([10, 20, 30, 255]), width=1, height=1)

    assert output.read_bytes() == b"P6\n1 1\n255\n" + bytes([30, 20, 10])


def test_select_capturable_windows_excludes_hidden_ime_helpers() -> None:
    def window(title: str, visible: bool, size: tuple[int, int]) -> TargetWindow:
        return TargetWindow(
            hwnd=len(title),
            pid=10,
            process_path=r"C:\Games\TKKN.EXE",
            title=title,
            visible=visible,
            minimized=False,
            window_rect=(0, 0, size[0], size[1]),
            client_origin=(0, 0),
            client_size=size,
            dpi=96,
        )

    game = window("特訓", True, (320, 240))
    windows = [
        game,
        window("MSCTFIME UI", False, (0, 0)),
        window("Default IME", False, (0, 0)),
    ]

    assert select_capturable_windows(windows, "tkkn.exe", "特訓") == [game]
