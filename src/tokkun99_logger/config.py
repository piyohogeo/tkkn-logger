"""Validated settings shared by the CLI and GUI front ends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CaptureBackend = Literal["wgc", "mss"]
RetentionMode = Literal["records_only", "collect_samples", "collect_all"]


@dataclass(frozen=True)
class LoggerConfig:
    fps: int = 30
    capture_backend: CaptureBackend = "wgc"
    retention_mode: RetentionMode = "records_only"
    auto_monitor: bool = False
    sample_every: int = 10
    min_free_gb: float = 2.0
    result_record_seconds: float = 10.0
    message_hold_seconds: float = 2.0
    save_run_images: bool = False
    log_result_frames: bool = False
    result_frame_log_limit: int = 300
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        if self.capture_backend not in ("wgc", "mss"):
            raise ValueError(f"Unsupported capture backend: {self.capture_backend}")
        if self.retention_mode not in ("records_only", "collect_samples", "collect_all"):
            raise ValueError(f"Unsupported retention mode: {self.retention_mode}")
        if self.sample_every <= 0 or self.result_frame_log_limit <= 0:
            raise ValueError("sample_every and result_frame_log_limit must be positive")
        if (
            self.min_free_gb < 0
            or self.result_record_seconds < 0
            or self.message_hold_seconds < 0
            or (self.duration_seconds is not None and self.duration_seconds < 0)
        ):
            raise ValueError("durations and free-space threshold must be non-negative")

    @property
    def minimum_free_bytes(self) -> int:
        return round(self.min_free_gb * 1024**3)
