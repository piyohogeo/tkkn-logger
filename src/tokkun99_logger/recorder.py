"""FFmpeg-backed run recording with pre-roll and atomic finalization."""

from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import shutil
import subprocess


class RecorderError(RuntimeError):
    pass


class RunRecorder:
    def __init__(
        self,
        *,
        ffmpeg_path: Path,
        width: int = 320,
        height: int = 240,
        fps: int = 30,
        pre_roll_seconds: float = 2.0,
    ) -> None:
        if width <= 0 or height <= 0 or fps <= 0 or pre_roll_seconds < 0:
            raise ValueError("Invalid recorder dimensions, FPS, or pre-roll")
        self.ffmpeg_path = ffmpeg_path.resolve()
        if not self.ffmpeg_path.is_file():
            raise FileNotFoundError(self.ffmpeg_path)
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_bytes = width * height * 3
        self.pre_roll = deque(maxlen=round(fps * pre_roll_seconds))
        self.process: subprocess.Popen[bytes] | None = None
        self.partial_path: Path | None = None
        self.final_path: Path | None = None
        self.frames_written = 0
        self.paused = False

    @property
    def active(self) -> bool:
        return self.process is not None

    def _validate_frame(self, frame: bytes) -> None:
        if len(frame) != self.frame_bytes:
            raise ValueError(f"Expected {self.frame_bytes} BGR bytes, got {len(frame)}")

    def observe(self, frame: bytes) -> None:
        """Keep pre-roll while idle, or write directly while recording."""
        self._validate_frame(frame)
        if self.active:
            if not self.paused:
                self.write(frame)
        else:
            self.pre_roll.append(frame)

    def clear_pre_roll(self) -> None:
        """Discard idle frames that must not carry into the next recording."""
        self.pre_roll.clear()

    def append_hold(self, frame: bytes, seconds: float) -> None:
        """Extend an active recording by repeating one frame without waiting."""
        self._validate_frame(frame)
        if seconds < 0:
            raise ValueError("Hold duration must be non-negative")
        if not self.active:
            raise RecorderError("Recorder is not active")
        if self.paused:
            raise RecorderError("Recorder is paused")
        for _ in range(round(self.fps * seconds)):
            self.write(frame)

    def pause(self) -> None:
        """Stop appending frames without closing the active FFmpeg process."""
        if not self.active:
            raise RecorderError("Recorder is not active")
        self.paused = True

    def resume(self) -> None:
        """Resume appending frames to an active recording."""
        if not self.active:
            raise RecorderError("Recorder is not active")
        self.paused = False

    def start(self, final_path: Path) -> None:
        if self.active:
            raise RecorderError("Recorder is already active")
        final_path = final_path.resolve()
        if final_path.suffix.casefold() != ".mp4":
            raise ValueError("Final recording path must end in .mp4")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep the final .mp4 name unavailable until FFmpeg has written the
        # trailer successfully.  The explicit ``-f mp4`` below means the
        # temporary filename does not need to end in .mp4.
        partial_path = final_path.with_name(f"{final_path.name}.incomplete")
        if partial_path.exists() or final_path.exists():
            raise FileExistsError(partial_path if partial_path.exists() else final_path)
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        command = self.build_command(partial_path)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
        )
        self.partial_path = partial_path
        self.final_path = final_path
        self.frames_written = 0
        self.paused = False
        buffered = list(self.pre_roll)
        self.pre_roll.clear()
        try:
            for frame in buffered:
                self.write(frame)
        except Exception:
            self._close_process()
            raise

    def build_command(self, partial_path: Path) -> list[str]:
        """Build the fixed LGPL-compatible MPEG-4 Part 2 command."""
        return [
            str(self.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{self.width}x{self.height}",
            "-framerate",
            str(self.fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "mpeg4",
            "-q:v",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(partial_path),
        ]

    def write(self, frame: bytes) -> None:
        self._validate_frame(frame)
        if self.process is None or self.process.stdin is None:
            raise RecorderError("Recorder is not active")
        try:
            self.process.stdin.write(frame)
            self.frames_written += 1
        except (BrokenPipeError, OSError) as exc:
            stderr = self.process.stderr.read().decode("utf-8", errors="replace") if self.process.stderr else ""
            raise RecorderError(f"FFmpeg input failed: {stderr}") from exc

    def _close_process(self) -> tuple[int, str]:
        if self.process is None:
            raise RecorderError("Recorder is not active")
        process = self.process
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        return_code = process.wait(timeout=30)
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        self.process = None
        self.paused = False
        return return_code, stderr

    def finalize(self) -> Path:
        if self.partial_path is None or self.final_path is None:
            raise RecorderError("Recording paths are not initialized")
        return_code, stderr = self._close_process()
        if return_code != 0 or not self.partial_path.is_file() or self.partial_path.stat().st_size == 0:
            raise RecorderError(f"FFmpeg finalization failed ({return_code}): {stderr}")
        os.replace(self.partial_path, self.final_path)
        result = self.final_path
        self.partial_path = None
        self.final_path = None
        return result

    def finalize_incomplete(self, incomplete_path: Path) -> Path:
        """Close a valid partial recording and retain it in quarantine."""
        if self.partial_path is None:
            raise RecorderError("Recording path is not initialized")
        return_code, stderr = self._close_process()
        if return_code != 0 or not self.partial_path.is_file() or self.partial_path.stat().st_size == 0:
            raise RecorderError(f"FFmpeg incomplete finalization failed ({return_code}): {stderr}")
        incomplete_path = incomplete_path.resolve()
        incomplete_path.parent.mkdir(parents=True, exist_ok=True)
        if incomplete_path.exists():
            raise FileExistsError(incomplete_path)
        os.replace(self.partial_path, incomplete_path)
        self.partial_path = None
        self.final_path = None
        return incomplete_path
