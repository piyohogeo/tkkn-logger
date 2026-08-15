"""Reusable live logger service shared by the CLI and GUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import threading
import time
import uuid

import cv2
import numpy as np

from .app_paths import AppPaths
from .capture import (
    TargetWindowUnavailable,
    create_capture,
    enable_per_monitor_dpi_awareness,
    locate_window,
)
from .config import LoggerConfig
from .logger_events import EventSink, LoggerEvent
from .maintenance import (
    InstanceLock,
    artifact_stem,
    discard_detached_video,
    ensure_disk_capacity,
    recover_partial_videos,
)
from .message_collector import MessageCollector
from .recorder import RunRecorder
from .regression_frames import RegressionFrameLogger
from .result_reader import ResultConsensus, ResultReader
from .state_detector import DebouncedStateDetector, GameState, StateClassifier
from .storage import RunFinalization, Storage


LOGGER = logging.getLogger(__name__)


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


class LoggerService:
    """Own the complete live-monitor lifecycle without depending on a UI."""

    def __init__(
        self,
        config: LoggerConfig,
        paths: AppPaths,
        event_sink: EventSink | None = None,
    ) -> None:
        self.config = config
        self.paths = paths
        self.event_sink = event_sink or (lambda _event: None)
        self.stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        with self._lifecycle_lock:
            return self._running

    def request_stop(self) -> None:
        self.stop_event.set()

    def emit(self, kind: str, message: str, **data: object) -> None:
        self.event_sink(LoggerEvent(kind=kind, message=message, data=dict(data)))

    def run(self) -> int:
        with self._lifecycle_lock:
            if self._running:
                raise RuntimeError("LoggerService is already running")
            self._running = True
        self.emit("service_starting", "監視を開始しています")
        result = 0
        try:
            self._execute()
        except KeyboardInterrupt:
            self.request_stop()
        except TargetWindowUnavailable as exc:
            if self.config.auto_monitor:
                self.emit("target_lost", str(exc))
            else:
                LOGGER.exception("Logger target window unavailable")
                self.emit(
                    "error",
                    f"{type(exc).__name__}: {exc}",
                    error_type=type(exc).__name__,
                )
                result = 1
        except Exception as exc:
            LOGGER.exception("Logger service failed")
            self.emit(
                "error",
                f"{type(exc).__name__}: {exc}",
                error_type=type(exc).__name__,
            )
            result = 1
        finally:
            with self._lifecycle_lock:
                self._running = False
            self.emit("service_stopped", "監視を停止しました", exit_code=result)
        return result

    def _execute(self) -> None:
        config = self.config
        paths = self.paths
        paths.validate()
        layout = paths.layout
        enable_per_monitor_dpi_awareness()
        instance_lock = InstanceLock(layout.lock)
        capture = None
        current: LiveRun | None = None
        consensus: ResultConsensus | None = None
        result_started_elapsed: float | None = None
        completed_runs = 0

        instance_lock.acquire()
        try:
            if self.stop_event.is_set():
                return
            storage = Storage(layout.database, paths.data_root)
            storage.initialize()
            recovery = recover_partial_videos(paths.data_root)
            if recovery.recovered:
                self.emit(
                    "recovery_completed",
                    f"放棄された録画を{len(recovery.recovered)}件回収しました",
                    count=len(recovery.recovered),
                )
            ensure_disk_capacity(paths.data_root, minimum_free_bytes=config.minimum_free_bytes)
            message_collector = MessageCollector(storage)
            result_reader = ResultReader(layout.glyph_profile)
            regression_logger = (
                RegressionFrameLogger(layout.regression / "results", config.result_frame_log_limit)
                if config.log_result_frames
                else None
            )
            detector = DebouncedStateDetector(StateClassifier(layout.state_profile), stable_frames=3)
            recorder = RunRecorder(
                ffmpeg_path=paths.ffmpeg_path,
                width=320,
                height=240,
                fps=config.fps,
                pre_roll_seconds=2.0,
            )
            window = locate_window()
            self.emit(
                "target_found",
                f"ゲームを検出しました（{window.client_size[0]}x{window.client_size[1]}）",
                target_size=window.client_size,
                hwnd=window.hwnd,
                capture_backend=config.capture_backend,
            )
            capture = create_capture(window, config.capture_backend, config.fps)
            started = time.perf_counter()
            next_frame = started
            last_window_refresh = 0.0
            last_status_second = -1
            interval = 1.0 / config.fps
            self.emit(
                "service_started",
                f"監視を開始しました（{config.capture_backend.upper()} / {config.fps} FPS）",
                capture_backend=config.capture_backend,
                fps=config.fps,
            )

            def finish_active_video() -> None:
                nonlocal current
                if current is None or not recorder.active:
                    return
                incomplete_stem = artifact_stem(None, current.started_at, current.run_id)
                incomplete = layout.videos / "incomplete" / f"{incomplete_stem}.mp4"
                recorder.finalize_incomplete(incomplete)
                current.video_relative = incomplete.relative_to(paths.data_root).as_posix()
                current.video_finalized = True
                self.emit(
                    "recording_finished",
                    "途中終了動画を安全に確定しました",
                    run_id=current.run_id,
                    incomplete=True,
                )

            def persist_current(status: str) -> None:
                nonlocal current, consensus, completed_runs, result_started_elapsed
                if current is None:
                    return
                ended_at = now_iso()
                stem = artifact_stem(current.survival_ms, current.started_at, current.run_id)
                result_relative = None
                if config.save_run_images and current.result_image is not None:
                    result_relative = f"collection/runs/{stem}_result.png"
                    result_path = paths.data_root / result_relative
                    result_path.parent.mkdir(parents=True, exist_ok=True)
                    if not cv2.imwrite(str(result_path), current.result_image):
                        raise OSError(f"Could not write {result_path}")
                if current.video_finalized and current.survival_ms is not None:
                    old_video = (paths.data_root / current.video_relative).resolve()
                    new_relative = f"collection/videos/{stem}.mp4"
                    new_video = (paths.data_root / new_relative).resolve()
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
                    capture_profile_id=f"{config.capture_backend}-320x240-{config.fps}fps-v1",
                    recognizer_version="state-v1+glyph-v2",
                )
                record = storage.finalize_run(finalization)
                regression_frames = 0
                if regression_logger is not None:
                    regression_frames = regression_logger.finalize(
                        status=status,
                        survival_ms=current.survival_ms,
                        bullet_count=current.bullet_count,
                    )
                retained = current.video_finalized
                if status == "complete":
                    completed_runs += 1
                    keep_sample = (
                        config.retention_mode == "collect_samples"
                        and completed_runs % config.sample_every == 0
                    )
                    keep_video = (
                        record.is_survival_record
                        or record.is_bullet_record
                        or config.retention_mode == "collect_all"
                        or keep_sample
                    )
                    if current.video_finalized and not keep_video:
                        retained = not discard_detached_video(storage, current.run_id, ended_at)
                kind = "run_completed" if status == "complete" else "run_needs_review"
                if status in ("incomplete", "error"):
                    kind = "run_incomplete"
                self.emit(
                    kind,
                    f"run {current.run_id}: {status}",
                    run_id=current.run_id,
                    status=status,
                    survival_ms=current.survival_ms,
                    bullet_count=current.bullet_count,
                    survival_record=record.is_survival_record,
                    bullet_record=record.is_bullet_record,
                    video_retained=retained,
                    message_cluster_id=current.message_cluster_id,
                    regression_frames=regression_frames,
                )
                current = None
                consensus = None
                result_started_elapsed = None

            try:
                while not self.stop_event.is_set() and (
                    config.duration_seconds is None
                    or time.perf_counter() - started < config.duration_seconds
                ):
                    now = time.perf_counter()
                    if now < next_frame:
                        self.stop_event.wait(next_frame - now)
                    if self.stop_event.is_set():
                        break
                    elapsed = time.perf_counter() - started
                    if elapsed - last_window_refresh >= 1.0:
                        refreshed = locate_window()
                        target_changed = refreshed.hwnd != window.hwnd
                        position_changed = (
                            config.capture_backend == "mss"
                            and refreshed.client_origin != window.client_origin
                        )
                        if target_changed or position_changed:
                            capture.close()
                            capture = create_capture(refreshed, config.capture_backend, config.fps)
                        window = refreshed
                        last_window_refresh = elapsed

                    bgra = capture.grab()
                    image = np.frombuffer(bgra, dtype=np.uint8).reshape(240, 320, 4)[:, :, :3].copy()
                    observation = detector.observe(image)
                    if observation.changed:
                        result_started_elapsed = (
                            elapsed if observation.state == GameState.RESULT else None
                        )
                    if recorder.active:
                        pause_due = (
                            observation.state == GameState.RESULT
                            and result_started_elapsed is not None
                            and elapsed - result_started_elapsed >= config.result_record_seconds
                        )
                        if pause_due and not recorder.paused:
                            recorder.pause()
                            self.emit(
                                "recording_paused",
                                f"RESULT表示が{config.result_record_seconds:g}秒続いたため録画を一時停止しました",
                                elapsed_seconds=elapsed,
                            )
                        elif observation.state != GameState.RESULT and recorder.paused:
                            recorder.resume()
                            self.emit(
                                "recording_resumed",
                                f"{observation.state.value}で録画を再開しました",
                                elapsed_seconds=elapsed,
                            )
                    recorder.observe(image.tobytes())
                    status_second = int(elapsed)
                    if status_second != last_status_second:
                        last_status_second = status_second
                        self.emit(
                            "service_status",
                            observation.state.value,
                            game_state=observation.state.value,
                            elapsed_seconds=elapsed,
                            recording=recorder.active,
                            recording_paused=recorder.paused,
                            recording_seconds=(
                                recorder.frames_written / config.fps if recorder.active else 0.0
                            ),
                        )

                    if observation.changed:
                        self.emit(
                            "state_changed",
                            f"状態: {observation.state.value}",
                            game_state=observation.state.value,
                            elapsed_seconds=elapsed,
                            title_score=observation.scores.title,
                            result_score=observation.scores.result,
                        )
                        if observation.state == GameState.TITLE:
                            recorder.clear_pre_roll()
                        if observation.state == GameState.PLAYING:
                            ensure_disk_capacity(
                                paths.data_root, minimum_free_bytes=config.minimum_free_bytes
                            )
                            if current is not None:
                                finish_active_video()
                                persist_current("incomplete")
                            run_id = str(uuid.uuid4())
                            started_at = now_iso()
                            pending_stem = artifact_stem(None, started_at, run_id)
                            video_relative = f"collection/videos/{pending_stem}.mp4"
                            current = LiveRun(run_id, started_at, video_relative)
                            if regression_logger is not None:
                                regression_logger.start(run_id, started_at)
                            recorder.start(paths.data_root / video_relative)
                            consensus = None
                            self.emit(
                                "recording_started",
                                "録画を開始しました",
                                run_id=run_id,
                                started_at=started_at,
                            )
                        elif observation.state == GameState.RESULT and current is not None:
                            current.result_image = image.copy()
                            consensus = ResultConsensus(required_frames=1)
                        elif observation.state == GameState.MESSAGE and current is not None:
                            resolved = consensus.resolve() if consensus is not None else None
                            if resolved and resolved.is_confirmed and resolved.reading:
                                current.survival_ms = resolved.reading.survival_ms
                                current.bullet_count = resolved.reading.bullet_count
                                current.score_confidence = resolved.reading.confidence
                            message_stem = artifact_stem(
                                current.survival_ms, current.started_at, current.run_id
                            )
                            assignment = message_collector.collect(
                                image,
                                now_iso(),
                                screen_relative_path=(
                                    f"collection/messages/{message_stem}_message.png"
                                ),
                            )
                            current.message_cluster_id = assignment.cluster_id
                            if recorder.active:
                                recorder.append_hold(image.tobytes(), config.message_hold_seconds)
                                recorder.finalize()
                                current.video_finalized = True
                                self.emit(
                                    "recording_finished",
                                    "録画を確定しました",
                                    run_id=current.run_id,
                                    incomplete=False,
                                )
                        elif observation.state == GameState.TITLE and current is not None:
                            complete = (
                                current.video_finalized
                                and current.survival_ms is not None
                                and current.bullet_count is not None
                                and current.message_cluster_id is not None
                            )
                            persist_current("complete" if complete else "needs_review")

                    if observation.state == GameState.RESULT and consensus is not None:
                        if regression_logger is not None and observation.candidate == GameState.RESULT:
                            regression_logger.add(image)
                        reading = result_reader.read(image)
                        consensus.add(reading)
                        if current is not None and not reading.needs_review:
                            current.result_image = image.copy()
                    next_frame += interval
            except KeyboardInterrupt:
                if current is not None:
                    finish_active_video()
                    persist_current("incomplete")
                raise
            except TargetWindowUnavailable:
                if current is not None:
                    finish_active_video()
                    persist_current("incomplete")
                raise
            except Exception:
                if current is not None:
                    finish_active_video()
                    persist_current("error")
                raise

            if current is not None:
                finish_active_video()
                persist_current("incomplete")
        finally:
            if capture is not None:
                capture.close()
            instance_lock.release()
