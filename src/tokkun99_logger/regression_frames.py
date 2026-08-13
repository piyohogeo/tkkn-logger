"""Optional lossless RESULT-frame logging for local regression evaluation."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


class RegressionFrameLogger:
    """Store distinct RESULT frames as bounded, lossless PNG samples."""

    def __init__(self, root: Path, maximum_frames: int = 300) -> None:
        if maximum_frames < 1:
            raise ValueError("maximum_frames must be positive")
        self.root = root
        self.maximum_frames = maximum_frames
        self.run_id: str | None = None
        self.started_at: str | None = None
        self.directory: Path | None = None
        self.saved_frames = 0
        self.duplicate_frames = 0
        self.dropped_frames = 0
        self._digests: set[bytes] = set()

    def start(self, run_id: str, started_at: str) -> None:
        if self.run_id is not None:
            raise RuntimeError("A regression frame run is already active")
        date_path = datetime.fromisoformat(started_at).strftime("%Y/%m/%d")
        self.run_id = run_id
        self.started_at = started_at
        self.directory = self.root / date_path / run_id
        self.saved_frames = 0
        self.duplicate_frames = 0
        self.dropped_frames = 0
        self._digests.clear()

    def add(self, frame: np.ndarray) -> Path | None:
        if self.run_id is None or self.directory is None:
            raise RuntimeError("No regression frame run is active")
        if self.saved_frames >= self.maximum_frames:
            self.dropped_frames += 1
            return None
        digest = hashlib.blake2b(frame.tobytes(), digest_size=16).digest()
        if digest in self._digests:
            self.duplicate_frames += 1
            return None
        self._digests.add(digest)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{self.saved_frames:06d}.png"
        written = cv2.imwrite(
            str(path),
            frame,
            [cv2.IMWRITE_PNG_COMPRESSION, 3],
        )
        if not written:
            raise OSError(f"Could not write {path}")
        self.saved_frames += 1
        return path

    def finalize(
        self,
        *,
        status: str,
        survival_ms: int | None,
        bullet_count: int | None,
    ) -> int:
        saved_frames = self.saved_frames
        if self.run_id is not None and self.directory is not None and self.directory.exists():
            manifest = {
                "version": 1,
                "run_id": self.run_id,
                "started_at": self.started_at,
                "status": status,
                "survival_ms": survival_ms,
                "bullet_count": bullet_count,
                "format": "PNG",
                "lossless": True,
                "saved_frames": self.saved_frames,
                "duplicate_frames": self.duplicate_frames,
                "dropped_frames": self.dropped_frames,
                "maximum_frames": self.maximum_frames,
            }
            (self.directory / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        self.run_id = None
        self.started_at = None
        self.directory = None
        self.saved_frames = 0
        self.duplicate_frames = 0
        self.dropped_frames = 0
        self._digests.clear()
        return saved_frames
