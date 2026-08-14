"""A/B benchmark MSS and WGC at the same output FPS; no game input is sent."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time

import win32pdh


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.maintenance import InstanceLock  # noqa: E402
from probe_capture import (  # noqa: E402
    MssCapture,
    WgcCapture,
    enable_per_monitor_dpi_awareness,
    enumerate_windows,
    select_capturable_windows,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "performance" / "capture_ab"


class DwmCpuSampler:
    def __init__(self) -> None:
        self.samples: list[float] = []
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="dwm-cpu-sampler", daemon=True)
        self._started = False

    def start(self) -> None:
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self) -> None:
        query = None
        try:
            query = win32pdh.OpenQuery()
            counter = win32pdh.AddEnglishCounter(query, r"\Process(dwm)\% Processor Time")
            win32pdh.CollectQueryData(query)
            while not self._stop.wait(1.0):
                win32pdh.CollectQueryData(query)
                _counter_type, value = win32pdh.GetFormattedCounterValue(
                    counter, win32pdh.PDH_FMT_DOUBLE
                )
                self.samples.append(float(value))
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            if query is not None:
                win32pdh.CloseQuery(query)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def summarize_dwm(sampler: DwmCpuSampler) -> dict[str, object]:
    return {
        "samples": len(sampler.samples),
        "average_percent": statistics.mean(sampler.samples) if sampler.samples else None,
        "median_percent": statistics.median(sampler.samples) if sampler.samples else None,
        "p95_percent": percentile(sampler.samples, 0.95),
        "maximum_percent": max(sampler.samples) if sampler.samples else None,
        "error": sampler.error,
        "scale_note": "PDH process percentage may exceed Task Manager's normalized display",
    }


def run_phase(name: str, duration: float, fps: float, window) -> dict[str, object]:
    hashes: set[bytes] = set()
    frames = 0
    capture = None
    sampler = DwmCpuSampler()
    try:
        if name == "mss":
            capture = MssCapture(*window.client_origin, *window.client_size)
        elif name == "wgc":
            capture = WgcCapture(window, fps)
        # Exclude backend/session startup from the steady-state FPS and CPU
        # comparison. The warm-up frame is intentionally not counted.
        if capture is not None:
            capture.grab()
        sampler.start()
        wall_started = time.perf_counter()
        process_started = time.process_time()
        interval = 1.0 / fps
        next_frame = wall_started
        while time.perf_counter() - wall_started < duration:
            now = time.perf_counter()
            if now < next_frame:
                time.sleep(next_frame - now)
            if capture is not None:
                frame = capture.grab()
                if len(frame) != window.client_size[0] * window.client_size[1] * 4:
                    raise RuntimeError(f"Unexpected {name} frame size: {len(frame)}")
                hashes.add(hashlib.blake2b(frame, digest_size=8).digest())
                frames += 1
            next_frame += interval
    finally:
        if capture is not None:
            capture.__exit__()
        sampler.stop()
    elapsed = time.perf_counter() - wall_started
    process_cpu = time.process_time() - process_started
    return {
        "backend": name,
        "elapsed_seconds": elapsed,
        "output_frames": frames,
        "effective_output_fps": frames / elapsed if frames else None,
        "unique_frames": len(hashes),
        "source_frames_arrived": getattr(capture, "frames_arrived", None),
        "wgc_os_update_throttle": getattr(capture, "os_update_throttle", None),
        "benchmark_process_cpu_percent": process_cpu / elapsed * 100,
        "dwm": summarize_dwm(sampler),
    }


def aggregate(phases: list[dict[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for backend in ("baseline", "mss", "wgc"):
        matching = [phase for phase in phases if phase["backend"] == backend]
        dwm = [phase["dwm"]["average_percent"] for phase in matching]  # type: ignore[index]
        dwm = [value for value in dwm if value is not None]
        process_cpu = [float(phase["benchmark_process_cpu_percent"]) for phase in matching]
        result[backend] = {
            "runs": len(matching),
            "mean_dwm_percent": statistics.mean(dwm) if dwm else None,
            "mean_benchmark_process_cpu_percent": statistics.mean(process_cpu),
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=10.0, help="Seconds per phase")
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration < 3 or args.cooldown < 0 or args.fps <= 0:
        raise SystemExit("duration must be >=3; cooldown must be non-negative; fps must be positive")
    enable_per_monitor_dpi_awareness()
    windows = select_capturable_windows(
        enumerate_windows("tkkn.exe", ""), "tkkn.exe", ""
    )
    if len(windows) != 1:
        raise SystemExit(f"Expected exactly one visible TKKN window; found {len(windows)}")
    window = windows[0]
    if window.client_size != (320, 240):
        raise SystemExit(f"Expected 320x240 client, got {window.client_size}")
    lock = InstanceLock(PROJECT_ROOT / "data" / "logger.lock")
    lock.acquire()
    phases: list[dict[str, object]] = []
    sequence = ("baseline", "mss", "wgc", "wgc", "mss", "baseline")
    try:
        for index, backend in enumerate(sequence, 1):
            print(f"Phase {index}/{len(sequence)}: {backend} ({args.duration:g}s)")
            phase = run_phase(backend, args.duration, args.fps, window)
            phases.append(phase)
            print(
                f"  DWM avg={phase['dwm']['average_percent']!s}%, "  # type: ignore[index]
                f"process={phase['benchmark_process_cpu_percent']:.2f}%, "
                f"fps={phase['effective_output_fps']}"
            )
            if index != len(sequence) and args.cooldown:
                time.sleep(args.cooldown)
    finally:
        lock.release()
    report = {
        "created_at": datetime.now().astimezone().isoformat(),
        "mode": "read_only_no_input_injection",
        "fps": args.fps,
        "seconds_per_phase": args.duration,
        "window": {
            "hwnd": window.hwnd,
            "client_size": window.client_size,
            "window_rect": window.window_rect,
        },
        "phases": phases,
        "summary": aggregate(phases),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / f"{datetime.now():%Y%m%dT%H%M%S}_capture_ab.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"A/B benchmark complete: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
