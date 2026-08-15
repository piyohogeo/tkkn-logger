"""Window discovery and MSS/WGC capture adapters used by live logging."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading
import time


@dataclass(frozen=True)
class TargetWindow:
    hwnd: int
    pid: int
    process_path: str | None
    title: str
    visible: bool
    minimized: bool
    window_rect: tuple[int, int, int, int]
    client_origin: tuple[int, int]
    client_size: tuple[int, int]
    dpi: int | None


def enable_per_monitor_dpi_awareness() -> str:
    """Make Win32 coordinates physical pixels where the OS supports it."""
    if os.name != "nt":
        return "unsupported"
    user32 = ctypes.windll.user32
    setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if setter is None:
        return "api_unavailable"
    setter.argtypes = [ctypes.c_void_p]
    setter.restype = wintypes.BOOL
    context = ctypes.c_void_p((1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 4)
    if setter(context):
        return "per_monitor_v2"
    return f"unchanged_winerror_{ctypes.get_last_error()}"


def process_path(pid: int) -> str | None:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def enumerate_windows(process_name: str, title_contains: str) -> list[TargetWindow]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    found: list[TargetWindow] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(max(1, title_length + 1))
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        title = title_buffer.value
        pid_value = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_value))
        exe_path = process_path(pid_value.value)
        exe_name = Path(exe_path).name if exe_path else ""
        if not (
            exe_name.casefold() == process_name.casefold()
            or (title_contains and title_contains.casefold() in title.casefold())
        ):
            return True
        outer = wintypes.RECT()
        client = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not user32.GetWindowRect(hwnd, ctypes.byref(outer)):
            return True
        if not user32.GetClientRect(hwnd, ctypes.byref(client)):
            return True
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        get_dpi = getattr(user32, "GetDpiForWindow", None)
        found.append(
            TargetWindow(
                hwnd=int(hwnd),
                pid=pid_value.value,
                process_path=exe_path,
                title=title,
                visible=bool(user32.IsWindowVisible(hwnd)),
                minimized=bool(user32.IsIconic(hwnd)),
                window_rect=(outer.left, outer.top, outer.right, outer.bottom),
                client_origin=(origin.x, origin.y),
                client_size=(client.right - client.left, client.bottom - client.top),
                dpi=int(get_dpi(hwnd)) if get_dpi is not None else None,
            )
        )
        return True

    callback_ref = callback_type(callback)
    user32.EnumWindows(callback_ref, 0)
    return found


def select_capturable_windows(
    windows: list[TargetWindow], process_name: str, title_contains: str
) -> list[TargetWindow]:
    """Prefer valid windows owned by the target process, excluding IME helpers."""
    process_matches = [
        window
        for window in windows
        if window.process_path
        and Path(window.process_path).name.casefold() == process_name.casefold()
    ]
    pool = process_matches or windows
    capturable = [
        window
        for window in pool
        if window.visible and not window.minimized and min(window.client_size) > 0
    ]
    exact_title = [
        window
        for window in capturable
        if title_contains and window.title.casefold() == title_contains.casefold()
    ]
    return exact_title or capturable


def locate_window(
    process_name: str = "tkkn.exe",
    title_contains: str = "特訓",
    expected_size: tuple[int, int] = (320, 240),
) -> TargetWindow:
    candidates = enumerate_windows(process_name, title_contains)
    capturable = select_capturable_windows(candidates, process_name, title_contains)
    if not capturable:
        raise RuntimeError("『特訓'99』が見つかりません")
    if len(capturable) != 1:
        raise RuntimeError(f"対象ウィンドウが複数あります: {len(capturable)}")
    window = capturable[0]
    if window.client_size != expected_size:
        raise RuntimeError(
            f"ゲーム画面が{expected_size[0]}x{expected_size[1]}ではありません: "
            f"{window.client_size[0]}x{window.client_size[1]}"
        )
    return window


class MssCapture:
    def __init__(self, left: int, top: int, width: int, height: int) -> None:
        from mss import MSS

        self.capture = MSS()
        self.region = {"left": left, "top": top, "width": width, "height": height}

    def grab(self) -> bytes:
        return bytes(self.capture.grab(self.region).bgra)

    def close(self) -> None:
        self.capture.close()

    def __enter__(self) -> "MssCapture":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def extended_frame_bounds(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), wintypes.DWORD(9), ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if result != 0:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def resolve_client_crop(
    frame_size: tuple[int, int], window: TargetWindow
) -> tuple[int, int, int, int]:
    frame_width, frame_height = frame_size
    client_width, client_height = window.client_size
    if frame_size == window.client_size:
        return 0, 0, client_width, client_height
    bounds_candidates = [window.window_rect]
    extended = extended_frame_bounds(window.hwnd)
    if extended is not None:
        bounds_candidates.insert(0, extended)
    client_x, client_y = window.client_origin
    for left, top, right, bottom in bounds_candidates:
        if (right - left, bottom - top) != frame_size:
            continue
        crop_left, crop_top = client_x - left, client_y - top
        crop_right, crop_bottom = crop_left + client_width, crop_top + client_height
        if 0 <= crop_left < crop_right <= frame_width and 0 <= crop_top < crop_bottom <= frame_height:
            return crop_left, crop_top, crop_right, crop_bottom
    raise RuntimeError(f"Cannot locate client {window.client_size} inside WGC frame {frame_size}")


class WgcCapture:
    """Latest-frame adapter for Windows Graphics Capture window frames."""

    def __init__(self, window: TargetWindow, fps: float = 30.0) -> None:
        from windows_capture import WindowsCapture

        if fps <= 0:
            raise ValueError("fps must be positive")
        self.window = window
        self._condition = threading.Condition()
        self._latest: bytes | None = None
        self._error: BaseException | None = None
        self._crop: tuple[int, int, int, int] | None = None
        self._frame_size: tuple[int, int] | None = None
        self.frames_arrived = 0
        modern_session_options = sys.getwindowsversion().build >= 26100
        self.os_update_throttle = modern_session_options
        self.capture = WindowsCapture(
            cursor_capture=False,
            draw_border=None,
            secondary_window=False if modern_session_options else None,
            minimum_update_interval=max(1, round(1000 / fps)) if modern_session_options else None,
            dirty_region=None,
            window_hwnd=window.hwnd,
        )
        self.capture.frame_handler = self._on_frame_arrived
        self.capture.closed_handler = self._on_closed
        self.control = self.capture.start_free_threaded()

    def _on_frame_arrived(self, frame, control) -> None:
        try:
            frame_size = (frame.width, frame.height)
            if self._crop is None or self._frame_size != frame_size:
                self._crop = resolve_client_crop(frame_size, self.window)
                self._frame_size = frame_size
            left, top, right, bottom = self._crop
            latest = frame.frame_buffer[top:bottom, left:right, :4].tobytes()
            expected = self.window.client_size[0] * self.window.client_size[1] * 4
            if len(latest) != expected:
                raise RuntimeError(f"Unexpected WGC client frame size: {len(latest)} != {expected}")
            with self._condition:
                self._latest = latest
                self.frames_arrived += 1
                self._condition.notify_all()
        except BaseException as exc:
            with self._condition:
                self._error = exc
                self._condition.notify_all()
            control.stop()

    def _on_closed(self) -> None:
        with self._condition:
            if self._error is None:
                self._error = RuntimeError("The WGC target window was closed")
            self._condition.notify_all()

    def grab(self, timeout: float = 5.0) -> bytes:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._latest is None and self._error is None:
                if self.control.is_finished():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(0.1, remaining))
            if self._error is not None:
                raise RuntimeError("WGC capture failed") from self._error
            if self._latest is not None:
                return self._latest
        if self.control.is_finished():
            try:
                self.control.wait()
            except Exception as exc:
                raise RuntimeError(f"WGC capture thread failed: {exc}") from exc
            raise RuntimeError("WGC capture thread stopped before delivering a frame")
        raise TimeoutError(f"WGC did not deliver a frame within {timeout:g} seconds")

    def close(self) -> None:
        if not self.control.is_finished():
            self.control.stop()
        self.control.wait()

    def __enter__(self) -> "WgcCapture":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def create_capture(window: TargetWindow, backend: str, fps: int):
    try:
        if backend == "wgc":
            return WgcCapture(window, fps)
        if backend == "mss":
            return MssCapture(*window.client_origin, *window.client_size)
    except ImportError as exc:
        raise RuntimeError(f"選択したキャプチャ方式を利用できません: {backend.upper()}") from exc
    raise ValueError(f"Unsupported capture backend: {backend}")
