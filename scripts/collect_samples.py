"""Collect a user-driven Tokkun '99 screen sequence without sending input."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import cv2
import numpy as np

try:
    from .probe_capture import MssCapture, enable_per_monitor_dpi_awareness, enumerate_windows, select_capturable_windows
except ImportError:  # Direct execution: python scripts/collect_samples.py
    from probe_capture import MssCapture, enable_per_monitor_dpi_awareness, enumerate_windows, select_capturable_windows


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "artifacts" / "calibration" / "sessions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-name", default="tkkn.exe")
    parser.add_argument("--title-contains", default="特訓")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--start-delay", type=float, default=3.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    return parser.parse_args()


def locate_unique_window(process_name: str, title_contains: str):
    candidates = enumerate_windows(process_name, title_contains)
    capturable = select_capturable_windows(candidates, process_name, title_contains)
    if len(capturable) != 1:
        raise RuntimeError(f"Expected one capturable target window; found {len(capturable)}")
    return capturable[0]


def save_png(path: Path, bgra: bytes, width: int, height: int) -> None:
    image = np.frombuffer(bgra, dtype=np.uint8).reshape(height, width, 4)
    if not cv2.imwrite(str(path), image[:, :, :3]):
        raise OSError(f"Could not write {path}")


def change_score(previous: bytes | None, current: bytes) -> float | None:
    if previous is None:
        return None
    before = np.frombuffer(previous, dtype=np.uint8).reshape(-1, 4)[:, :3]
    after = np.frombuffer(current, dtype=np.uint8).reshape(-1, 4)[:, :3]
    return float(np.abs(after.astype(np.int16) - before.astype(np.int16)).mean())


def main() -> int:
    args = parse_args()
    if args.duration <= 0 or args.fps <= 0 or args.start_delay < 0:
        raise SystemExit("duration/fps must be positive and start-delay must be non-negative")
    dpi_awareness = enable_per_monitor_dpi_awareness()
    initial_window = locate_unique_window(args.process_name, args.title_contains)
    if initial_window.client_size != (320, 240):
        raise SystemExit(f"Unexpected client size: {initial_window.client_size}; expected 320x240")

    session_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    session_dir = args.output_root.resolve() / session_id
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=False)
    events_path = session_dir / "frames.jsonl"
    manifest_path = session_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "session_id": session_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "mode": "user_driven_no_input_injection",
        "requested_duration_seconds": args.duration,
        "requested_fps": args.fps,
        "dpi_awareness": dpi_awareness,
        "initial_window": initial_window.__dict__,
        "expected_sequence": ["TITLE", "PLAYING", "RESULT", "MESSAGE", "TITLE"],
        "labels_confirmed": False,
        "status": "collecting",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Collection starts in {args.start_delay:g} seconds. Focus the game and play one short run.")
    time.sleep(args.start_delay)
    interval = 1.0 / args.fps
    started = time.perf_counter()
    next_frame = started
    frame_count = 0
    unique_count = 0
    previous_frame: bytes | None = None
    previous_hash: str | None = None
    last_window_refresh = 0.0
    window = initial_window
    capture: MssCapture | None = None
    status = "complete"
    error: str | None = None

    try:
        capture = MssCapture(*window.client_origin, *window.client_size)
        with events_path.open("w", encoding="utf-8", newline="\n") as events:
            while time.perf_counter() - started < args.duration:
                now = time.perf_counter()
                if now < next_frame:
                    time.sleep(next_frame - now)
                captured_at = time.perf_counter()
                elapsed = captured_at - started
                if elapsed - last_window_refresh >= 1.0:
                    refreshed = locate_unique_window(args.process_name, args.title_contains)
                    if refreshed.client_size != (320, 240):
                        raise RuntimeError(f"Client size changed to {refreshed.client_size}")
                    if refreshed.client_origin != window.client_origin:
                        capture.__exit__()
                        capture = MssCapture(*refreshed.client_origin, *refreshed.client_size)
                    window = refreshed
                    last_window_refresh = elapsed

                frame = capture.grab()
                digest = hashlib.sha256(frame).hexdigest()
                changed = digest != previous_hash
                relative_path: str | None = None
                if changed:
                    relative_path = f"frames/{frame_count:06d}.png"
                    save_png(session_dir / relative_path, frame, *window.client_size)
                    unique_count += 1
                event = {
                    "index": frame_count,
                    "captured_at": datetime.now().astimezone().isoformat(),
                    "elapsed_seconds": elapsed,
                    "sha256": digest,
                    "changed": changed,
                    "change_score": change_score(previous_frame, frame),
                    "saved_path": relative_path,
                    "window": {
                        "hwnd": window.hwnd,
                        "client_origin": window.client_origin,
                        "client_size": window.client_size,
                        "dpi": window.dpi,
                    },
                    "state_label": None,
                }
                events.write(json.dumps(event, ensure_ascii=False) + "\n")
                if frame_count % 30 == 0:
                    events.flush()
                frame_count += 1
                previous_frame = frame
                previous_hash = digest
                next_frame += interval
    except Exception as exc:
        status = "incomplete"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if capture is not None:
            capture.__exit__()

    elapsed_total = time.perf_counter() - started
    manifest.update(
        {
            "status": status,
            "error": error,
            "ended_at": datetime.now().astimezone().isoformat(),
            "elapsed_seconds": elapsed_total,
            "frame_count": frame_count,
            "unique_frame_count": unique_count,
            "effective_fps": frame_count / elapsed_total if elapsed_total else 0,
            "events_path": "frames.jsonl",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collection {status}: {session_dir}")
    print(f"Frames: {frame_count}, unique images: {unique_count}, effective FPS: {manifest['effective_fps']:.2f}")
    if error:
        print(error)
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
