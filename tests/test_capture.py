from __future__ import annotations

import pytest

from tokkun99_logger.capture import TargetWindow, create_capture, locate_window


def window(*, size: tuple[int, int] = (320, 240)) -> TargetWindow:
    return TargetWindow(1, 2, "tkkn.exe", "特訓", True, False, (0, 0, 328, 269), (4, 25), size, 96)


def test_locate_window_rejects_missing_multiple_and_wrong_size(monkeypatch) -> None:
    monkeypatch.setattr("tokkun99_logger.capture.enumerate_windows", lambda *_: [])
    with pytest.raises(RuntimeError, match="見つかりません"):
        locate_window()

    monkeypatch.setattr("tokkun99_logger.capture.enumerate_windows", lambda *_: [window(), window()])
    with pytest.raises(RuntimeError, match="複数"):
        locate_window()

    monkeypatch.setattr(
        "tokkun99_logger.capture.enumerate_windows", lambda *_: [window(size=(640, 480))]
    )
    with pytest.raises(RuntimeError, match="320x240"):
        locate_window()


def test_capture_backend_failure_is_explicit_and_does_not_fall_back(monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise ImportError("missing")

    monkeypatch.setattr("tokkun99_logger.capture.WgcCapture", unavailable)

    with pytest.raises(RuntimeError, match="WGC"):
        create_capture(window(), "wgc", 30)
