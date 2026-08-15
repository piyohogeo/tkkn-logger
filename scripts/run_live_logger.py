"""CLI front end for the observation-only Tokkun '99 logger service."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.app_paths import AppPaths  # noqa: E402
from tokkun99_logger.config import LoggerConfig  # noqa: E402
from tokkun99_logger.logger_events import LoggerEvent  # noqa: E402
from tokkun99_logger.logger_service import LoggerService  # noqa: E402
from tokkun99_logger.logging_setup import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120.0, help="0 runs until Ctrl+C")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--capture-backend",
        choices=("wgc", "mss"),
        default="wgc",
        help="Screen capture backend; WGC is the default",
    )
    parser.add_argument("--ffmpeg", type=Path, default=Path(r"C:\tools\ffmpeg\bin\ffmpeg.exe"))
    parser.add_argument(
        "--mode",
        choices=("records_only", "collect_samples", "collect_all"),
        default="records_only",
        help="Video retention policy",
    )
    parser.add_argument("--sample-every", type=int, default=10)
    parser.add_argument("--min-free-gb", type=float, default=2.0)
    parser.add_argument("--result-record-seconds", type=float, default=10.0)
    parser.add_argument("--message-hold-seconds", type=float, default=2.0)
    parser.add_argument("--save-run-images", action="store_true")
    parser.add_argument("--log-result-frames", action="store_true")
    parser.add_argument("--result-frame-log-limit", type=int, default=300)
    return parser.parse_args()


def console_event(event: LoggerEvent) -> None:
    if event.kind == "service_status":
        return
    if event.kind.startswith("run_"):
        values = event.data
        print(
            f"Run {values.get('run_id')}: status={values.get('status')}, "
            f"survival={values.get('survival_ms')}, bullets={values.get('bullet_count')}, "
            f"survival_record={values.get('survival_record')}, "
            f"bullet_record={values.get('bullet_record')}, "
            f"video_retained={values.get('video_retained')}"
        )
        return
    print(event.message)


def main() -> int:
    args = parse_args()
    try:
        config = LoggerConfig(
            fps=args.fps,
            capture_backend=args.capture_backend,
            retention_mode=args.mode,
            sample_every=args.sample_every,
            min_free_gb=args.min_free_gb,
            result_record_seconds=args.result_record_seconds,
            message_hold_seconds=args.message_hold_seconds,
            save_run_images=args.save_run_images,
            log_result_frames=args.log_result_frames,
            result_frame_log_limit=args.result_frame_log_limit,
            duration_seconds=None if args.duration == 0 else args.duration,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    paths = AppPaths.for_development(PROJECT_ROOT, ffmpeg_path=args.ffmpeg)
    configure_logging(paths.layout.log)
    return LoggerService(config, paths, console_event).run()


if __name__ == "__main__":
    raise SystemExit(main())
