"""Integrated user-driven logger smoke run; this script never sends input."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import time
import uuid

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.message_collector import MessageCollector  # noqa: E402
from tokkun99_logger.maintenance import (  # noqa: E402
    InstanceLock,
    artifact_stem,
    discard_detached_video,
    ensure_disk_capacity,
    recover_partial_videos,
)
from tokkun99_logger.recorder import RecorderError, RunRecorder  # noqa: E402
from tokkun99_logger.result_reader import ResultConsensus, ResultReader  # noqa: E402
from tokkun99_logger.state_detector import DebouncedStateDetector, GameState, StateClassifier  # noqa: E402
from tokkun99_logger.storage import RunFinalization, Storage  # noqa: E402
from probe_capture import MssCapture, enable_per_monitor_dpi_awareness, enumerate_windows, select_capturable_windows  # noqa: E402


DATA_ROOT = PROJECT_ROOT / "data"
STATE_PROFILE = DATA_ROOT / "templates" / "states" / "v1" / "profile.json"
GLYPH_PROFILE = DATA_ROOT / "templates" / "glyphs" / "v1" / "profile.json"


@dataclass
class LiveRun:
    run_id: str
    started_at: str
    video_relative: str
    result_image: np.ndarray | None = None
    survival_ms: int | None = None
    bullet_count: int | None = None
    score_confidence: float = 0.0
    message_cluster_id: int | None = None
    video_finalized: bool = False


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def locate_window():
    candidates = enumerate_windows("tkkn.exe", "特訓")
    capturable = select_capturable_windows(candidates, "tkkn.exe", "特訓")
    if len(capturable) != 1:
        raise RuntimeError(f"Expected one capturable TKKN window; found {len(capturable)}")
    window = capturable[0]
    if window.client_size != (320, 240):
        raise RuntimeError(f"Expected 320x240 client, got {window.client_size}")
    return window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120.0, help="0 runs until Ctrl+C")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--ffmpeg", type=Path, default=Path(r"C:\tools\ffmpeg\bin\ffmpeg.exe"))
    parser.add_argument(
        "--mode",
        choices=("records_only", "collect_samples", "collect_all"),
        default="records_only",
        help="Video retention policy (RESULT images are always retained)",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=10,
        help="In collect_samples mode, retain every Nth completed non-record video",
    )
    parser.add_argument("--min-free-gb", type=float, default=2.0)
    parser.add_argument(
        "--result-record-seconds",
        type=float,
        default=10.0,
        help="Pause video after this many seconds continuously on RESULT",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.duration < 0
        or args.fps <= 0
        or args.sample_every <= 0
        or args.min_free_gb < 0
        or args.result_record_seconds < 0
    ):
        raise SystemExit("duration/free space must be non-negative; fps/sample-every must be positive")
    enable_per_monitor_dpi_awareness()
    instance_lock = InstanceLock(DATA_ROOT / "logger.lock")
    instance_lock.acquire()
    storage = Storage(DATA_ROOT / "logger.sqlite3", DATA_ROOT)
    storage.initialize()
    recovery = recover_partial_videos(DATA_ROOT)
    if recovery.recovered:
        print(f"Recovered {len(recovery.recovered)} abandoned partial video(s) to quarantine.")
    minimum_free_bytes = round(args.min_free_gb * 1024**3)
    ensure_disk_capacity(DATA_ROOT, minimum_free_bytes=minimum_free_bytes)
    message_collector = MessageCollector(storage)
    result_reader = ResultReader(GLYPH_PROFILE)
    detector = DebouncedStateDetector(StateClassifier(STATE_PROFILE), stable_frames=3)
    recorder = RunRecorder(
        ffmpeg_path=args.ffmpeg,
        width=320,
        height=240,
        fps=args.fps,
        pre_roll_seconds=2.0,
    )
    window = locate_window()
    capture = MssCapture(*window.client_origin, *window.client_size)
    current: LiveRun | None = None
    consensus: ResultConsensus | None = None
    started = time.perf_counter()
    next_frame = started
    last_window_refresh = 0.0
    completed_runs = 0
    result_started_elapsed: float | None = None
    interval = 1.0 / args.fps
    print("Live logger started (observation only; no input injection).")

    def persist_current(status: str) -> None:
        nonlocal current, consensus, completed_runs, result_started_elapsed
        if current is None:
            return
        ended_at = now_iso()
        stem = artifact_stem(current.survival_ms, current.started_at, current.run_id)
        result_relative = None
        if current.result_image is not None:
            date_path = datetime.fromisoformat(current.started_at).strftime("%Y/%m/%d")
            result_relative = f"runs/{date_path}/{stem}_result.png"
            result_path = DATA_ROOT / result_relative
            result_path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(result_path), current.result_image):
                raise OSError(f"Could not write {result_path}")
        if current.video_finalized and current.survival_ms is not None:
            old_video = (DATA_ROOT / current.video_relative).resolve()
            new_relative = f"videos/collection/{stem}.mp4"
            new_video = (DATA_ROOT / new_relative).resolve()
            if old_video != new_video:
                new_video.parent.mkdir(parents=True, exist_ok=True)
                if new_video.exists():
                    raise FileExistsError(new_video)
                old_video.replace(new_video)
                current.video_relative = new_relative
        finalization = RunFinalization(
            run_id=current.run_id,
            started_at=current.started_at,
            ended_at=ended_at,
            survival_ms=current.survival_ms,
            bullet_count=current.bullet_count,
            score_confidence=current.score_confidence,
            status=status,
            video_path=current.video_relative if current.video_finalized else None,
            result_frame_path=result_relative,
            message_cluster_id=current.message_cluster_id,
            capture_profile_id="mss-320x240-30fps-v1",
            recognizer_version="state-v1+glyph-v1",
        )
        result = storage.finalize_run(finalization)
        retained = current.video_finalized
        if status == "complete":
            completed_runs += 1
            keep_nonrecord_sample = (
                args.mode == "collect_samples" and completed_runs % args.sample_every == 0
            )
            keep_video = (
                result.is_survival_record
                or result.is_bullet_record
                or args.mode == "collect_all"
                or keep_nonrecord_sample
            )
            if current.video_finalized and not keep_video:
                retained = not discard_detached_video(storage, current.run_id, ended_at)
        print(
            f"Run {current.run_id}: status={status}, survival={current.survival_ms}, "
            f"bullets={current.bullet_count}, survival_record={result.is_survival_record}, "
            f"bullet_record={result.is_bullet_record}, video_retained={retained}"
        )
        current = None
        consensus = None
        result_started_elapsed = None

    try:
        while args.duration == 0 or time.perf_counter() - started < args.duration:
            now = time.perf_counter()
            if now < next_frame:
                time.sleep(next_frame - now)
            elapsed = time.perf_counter() - started
            if elapsed - last_window_refresh >= 1.0:
                refreshed = locate_window()
                if refreshed.client_origin != window.client_origin:
                    capture.__exit__()
                    capture = MssCapture(*refreshed.client_origin, *refreshed.client_size)
                window = refreshed
                last_window_refresh = elapsed

            bgra = capture.grab()
            image = np.frombuffer(bgra, dtype=np.uint8).reshape(240, 320, 4)[:, :, :3].copy()
            observation = detector.observe(image)
            if observation.changed:
                result_started_elapsed = elapsed if observation.state == GameState.RESULT else None
            if recorder.active:
                result_pause_due = (
                    observation.state == GameState.RESULT
                    and result_started_elapsed is not None
                    and elapsed - result_started_elapsed >= args.result_record_seconds
                )
                if result_pause_due and not recorder.paused:
                    recorder.pause()
                    print(
                        f"{elapsed:8.2f}s recording paused after "
                        f"{args.result_record_seconds:g}s on RESULT"
                    )
                elif observation.state != GameState.RESULT and recorder.paused:
                    recorder.resume()
                    print(f"{elapsed:8.2f}s recording resumed on {observation.state.value}")
            recorder.observe(image.tobytes())
            if observation.changed:
                print(
                    f"{elapsed:8.2f}s state={observation.state.value} "
                    f"title={observation.scores.title:.3f} result={observation.scores.result:.3f}"
                )

                if observation.state == GameState.PLAYING:
                    ensure_disk_capacity(DATA_ROOT, minimum_free_bytes=minimum_free_bytes)
                    if current is not None:
                        if recorder.active:
                            incomplete_stem = artifact_stem(None, current.started_at, current.run_id)
                            incomplete = DATA_ROOT / "videos" / "incomplete" / f"{incomplete_stem}.mp4"
                            recorder.finalize_incomplete(incomplete)
                            current.video_relative = incomplete.relative_to(DATA_ROOT).as_posix()
                            current.video_finalized = True
                        persist_current("incomplete")
                    run_id = str(uuid.uuid4())
                    started_at = now_iso()
                    pending_stem = artifact_stem(None, started_at, run_id)
                    video_relative = f"videos/collection/{pending_stem}.mp4"
                    current = LiveRun(run_id, started_at, video_relative)
                    recorder.start(DATA_ROOT / video_relative)
                    consensus = None

                elif observation.state == GameState.RESULT and current is not None:
                    current.result_image = image.copy()
                    consensus = ResultConsensus(required_frames=5)

                elif observation.state == GameState.MESSAGE and current is not None:
                    resolved = consensus.resolve() if consensus is not None else None
                    if resolved and resolved.is_confirmed and resolved.reading:
                        current.survival_ms = resolved.reading.survival_ms
                        current.bullet_count = resolved.reading.bullet_count
                        current.score_confidence = resolved.reading.confidence
                    assignment = message_collector.collect(image, now_iso())
                    current.message_cluster_id = assignment.cluster_id
                    if recorder.active:
                        recorder.finalize()
                        current.video_finalized = True

                elif observation.state == GameState.TITLE and current is not None:
                    complete = (
                        current.video_finalized
                        and current.survival_ms is not None
                        and current.bullet_count is not None
                        and current.message_cluster_id is not None
                    )
                    persist_current("complete" if complete else "needs_review")

            if observation.state == GameState.RESULT and consensus is not None:
                reading = result_reader.read(image)
                consensus.add(reading)
                if current is not None and not reading.needs_review:
                    current.result_image = image.copy()
            next_frame += interval
    except KeyboardInterrupt:
        print("Interrupted by user; retaining active run as incomplete.")
    except Exception as exc:
        print(f"Live logger error: {type(exc).__name__}: {exc}")
        if current is not None:
            if recorder.active:
                incomplete_stem = artifact_stem(None, current.started_at, current.run_id)
                incomplete = DATA_ROOT / "videos" / "incomplete" / f"{incomplete_stem}.mp4"
                recorder.finalize_incomplete(incomplete)
                current.video_relative = incomplete.relative_to(DATA_ROOT).as_posix()
                current.video_finalized = True
            persist_current("error")
        return 1
    finally:
        capture.__exit__()
        instance_lock.release()

    if current is not None:
        if recorder.active:
            incomplete_stem = artifact_stem(None, current.started_at, current.run_id)
            incomplete = DATA_ROOT / "videos" / "incomplete" / f"{incomplete_stem}.mp4"
            recorder.finalize_incomplete(incomplete)
            current.video_relative = incomplete.relative_to(DATA_ROOT).as_posix()
            current.video_finalized = True
        persist_current("incomplete")
    print("Live logger finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
