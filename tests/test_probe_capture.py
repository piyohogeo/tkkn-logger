from __future__ import annotations

from scripts.probe_capture import TargetWindow, frame_stats, save_ppm, select_capturable_windows


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
