"""Read-only window and capture probe for Tokkun '99.

The probe never sends input to the game. It locates a single target window,
captures only its client rectangle, and records timing/quality measurements.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "calibration" / "capture_probe"


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
    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == (HANDLE)-4
    context = ctypes.c_void_p((1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 4)
    if setter(context):
        return "per_monitor_v2"
    # ERROR_ACCESS_DENIED commonly means awareness was already established.
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
    process_query_limited_information = 0x1000
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        query = kernel32.QueryFullProcessImageNameW
        if query(handle, 0, buffer, ctypes.byref(size)):
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
        process_match = exe_name.casefold() == process_name.casefold()
        title_match = bool(title_contains) and title_contains.casefold() in title.casefold()
        if not (process_match or title_match):
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
        dpi = int(get_dpi(hwnd)) if get_dpi is not None else None
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
                dpi=dpi,
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
        if window.visible
        and not window.minimized
        and min(window.client_size) > 0
    ]
    exact_title = [
        window
        for window in capturable
        if title_contains and window.title.casefold() == title_contains.casefold()
    ]
    return exact_title or capturable


class GdiCapture:
    """Visible-desktop capture using Win32 GDI, with no third-party imports."""

    def __init__(self, left: int, top: int, width: int, height: int) -> None:
        self.left, self.top, self.width, self.height = left, top, width, height
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32
        self.user32.GetDC.argtypes = [wintypes.HWND]
        self.user32.GetDC.restype = wintypes.HDC
        self.user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.user32.ReleaseDC.restype = ctypes.c_int
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteObject.restype = wintypes.BOOL
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi32.DeleteDC.restype = wintypes.BOOL
        self.screen_dc = self.user32.GetDC(0)
        self.memory_dc = self.gdi32.CreateCompatibleDC(self.screen_dc)
        self.bitmap = self.gdi32.CreateCompatibleBitmap(self.screen_dc, width, height)
        self.old_object = self.gdi32.SelectObject(self.memory_dc, self.bitmap)

        class BitmapInfoHeader(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BitmapInfo(ctypes.Structure):
            _fields_ = [("bmiHeader", BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 3)]

        self.bitmap_info = BitmapInfo()
        self.bitmap_info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
        self.bitmap_info.bmiHeader.biWidth = width
        self.bitmap_info.bmiHeader.biHeight = -height  # top-down image
        self.bitmap_info.bmiHeader.biPlanes = 1
        self.bitmap_info.bmiHeader.biBitCount = 32
        self.bitmap_info.bmiHeader.biCompression = 0  # BI_RGB
        self.buffer = ctypes.create_string_buffer(width * height * 4)

    def grab(self) -> bytes:
        srccopy, captureblt = 0x00CC0020, 0x40000000
        if not self.gdi32.BitBlt(
            self.memory_dc,
            0,
            0,
            self.width,
            self.height,
            self.screen_dc,
            self.left,
            self.top,
            srccopy | captureblt,
        ):
            raise OSError("BitBlt failed")
        rows = self.gdi32.GetDIBits(
            self.memory_dc,
            self.bitmap,
            0,
            self.height,
            self.buffer,
            ctypes.byref(self.bitmap_info),
            0,
        )
        if rows != self.height:
            raise OSError(f"GetDIBits returned {rows} of {self.height} rows")
        return self.buffer.raw

    def close(self) -> None:
        if self.old_object:
            self.gdi32.SelectObject(self.memory_dc, self.old_object)
        if self.bitmap:
            self.gdi32.DeleteObject(self.bitmap)
        if self.memory_dc:
            self.gdi32.DeleteDC(self.memory_dc)
        if self.screen_dc:
            self.user32.ReleaseDC(0, self.screen_dc)

    def __enter__(self) -> "GdiCapture":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class MssCapture:
    def __init__(self, left: int, top: int, width: int, height: int) -> None:
        from mss import MSS

        self.capture = MSS()
        self.region = {"left": left, "top": top, "width": width, "height": height}

    def grab(self) -> bytes:
        return bytes(self.capture.grab(self.region).bgra)

    def __enter__(self) -> "MssCapture":
        return self

    def __exit__(self, *_args: object) -> None:
        self.capture.close()


def frame_stats(frame: bytes) -> tuple[float, float]:
    pixels = len(frame) // 4
    stride = max(1, pixels // 4096)
    black = 0
    brightness_sum = 0.0
    sampled = 0
    for pixel in range(0, pixels, stride):
        offset = pixel * 4
        blue, green, red = frame[offset], frame[offset + 1], frame[offset + 2]
        black += int(max(red, green, blue) <= 5)
        brightness_sum += (red + green + blue) / 3
        sampled += 1
    return black / sampled, brightness_sum / sampled


def save_ppm(path: Path, frame: bytes, width: int, height: int) -> None:
    rgb = bytearray(width * height * 3)
    for pixel in range(width * height):
        source, target = pixel * 4, pixel * 3
        rgb[target] = frame[source + 2]
        rgb[target + 1] = frame[source + 1]
        rgb[target + 2] = frame[source]
    with path.open("wb") as output:
        output.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        output.write(rgb)


def probe_backend(
    backend: str,
    factory: Callable[[int, int, int, int], object],
    window: TargetWindow,
    duration: float,
    fps: float,
    output: Path,
) -> dict[str, object]:
    left, top = window.client_origin
    width, height = window.client_size
    timestamps: list[float] = []
    hashes: list[str] = []
    black_fractions: list[float] = []
    brightness: list[float] = []
    first_frame: bytes | None = None
    last_frame: bytes | None = None
    interval = 1.0 / fps
    started = time.perf_counter()
    next_frame = started
    with factory(left, top, width, height) as capture:  # type: ignore[attr-defined]
        while time.perf_counter() - started < duration:
            now = time.perf_counter()
            if now < next_frame:
                time.sleep(next_frame - now)
            captured_at = time.perf_counter()
            frame = capture.grab()  # type: ignore[attr-defined]
            if len(frame) != width * height * 4:
                raise RuntimeError(f"Unexpected frame size: {len(frame)}")
            if first_frame is None:
                first_frame = frame
            last_frame = frame
            timestamps.append(captured_at)
            hashes.append(hashlib.sha256(frame).hexdigest())
            black, mean_brightness = frame_stats(frame)
            black_fractions.append(black)
            brightness.append(mean_brightness)
            next_frame += interval
    elapsed = time.perf_counter() - started
    assert first_frame is not None and last_frame is not None
    save_ppm(output / f"{backend}_first.ppm", first_frame, width, height)
    save_ppm(output / f"{backend}_last.ppm", last_frame, width, height)
    intervals = [right - left for left, right in zip(timestamps, timestamps[1:])]
    return {
        "backend": backend,
        "frames": len(timestamps),
        "elapsed_seconds": elapsed,
        "effective_fps": len(timestamps) / elapsed,
        "mean_interval_ms": statistics.mean(intervals) * 1000 if intervals else None,
        "p95_interval_ms": sorted(intervals)[int(0.95 * (len(intervals) - 1))] * 1000 if intervals else None,
        "duplicate_ratio": 1.0 - len(set(hashes)) / len(hashes),
        "mean_black_fraction": statistics.mean(black_fractions),
        "mean_brightness": statistics.mean(brightness),
        "first_sha256": hashes[0],
        "last_sha256": hashes[-1],
        "capture_constraint": "visible desktop pixels; minimized or occluded windows are not reliable",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-name", default="tkkn.exe")
    parser.add_argument("--title-contains", default="特訓")
    parser.add_argument("--backend", choices=("auto", "mss", "gdi"), default="auto")
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.name != "nt":
        raise SystemExit("This probe supports Windows only.")
    if args.duration <= 0 or args.fps <= 0:
        raise SystemExit("--duration and --fps must be positive.")
    dpi_awareness = enable_per_monitor_dpi_awareness()
    windows = enumerate_windows(args.process_name, args.title_contains)
    capturable_windows = select_capturable_windows(windows, args.process_name, args.title_contains)
    report: dict[str, object] = {
        "created_at": datetime.now().astimezone().isoformat(),
        "mode": "read_only_no_input_injection",
        "python": {"version": sys.version, "executable": sys.executable},
        "dpi_awareness": dpi_awareness,
        "selection": {"process_name": args.process_name, "title_contains": args.title_contains},
        "candidates": [asdict(window) for window in windows],
        "capturable_candidates": [asdict(window) for window in capturable_windows],
        "results": [],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "report.json"
    if len(capturable_windows) != 1:
        report["status"] = "target_not_found" if not capturable_windows else "multiple_targets"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Expected exactly one capturable target window; found {len(capturable_windows)}. Report: {report_path}")
        return 2
    window = capturable_windows[0]

    backends: list[tuple[str, Callable[[int, int, int, int], object]]] = []
    if args.backend in ("auto", "mss"):
        try:
            import mss  # noqa: F401

            backends.append(("mss", MssCapture))
        except ImportError as exc:
            report["mss_unavailable"] = str(exc)
            if args.backend == "mss":
                report["status"] = "backend_unavailable"
    if args.backend in ("auto", "gdi"):
        backends.append(("gdi", GdiCapture))

    failures: list[dict[str, str]] = []
    for name, factory in backends:
        try:
            result = probe_backend(name, factory, window, args.duration, args.fps, args.output)
            report["results"].append(result)  # type: ignore[union-attr]
        except Exception as exc:
            failures.append({"backend": name, "error": f"{type(exc).__name__}: {exc}"})
    report["failures"] = failures
    report["status"] = "complete" if report["results"] else "failed"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Capture probe status: {report['status']}. Report: {report_path}")
    return 0 if report["results"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
