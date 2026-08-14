"""Startup recovery, disk guards, and safe video retention helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import re
import shutil

from .storage import Storage


SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9-]+$")


def artifact_stem(survival_ms: int | None, started_at: str, run_id: str) -> str:
    """Build a Windows-safe name sortable by survival time, then start datetime."""
    if survival_ms is not None and survival_ms < 0:
        raise ValueError("survival_ms must be non-negative")
    if not SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError(f"Unsafe run_id for file name: {run_id}")
    started = datetime.fromisoformat(started_at)
    if started.tzinfo is None:
        raise ValueError("started_at must include a timezone")
    score = f"{survival_ms:012d}ms" if survival_ms is not None else "unknown"
    timestamp = started.strftime("%Y-%m-%d_%H-%M-%S%z")
    return f"{score}_{timestamp}_{run_id}"


@dataclass(frozen=True)
class RecoveryResult:
    recovered: tuple[Path, ...]


class InstanceLock:
    """Non-blocking single-process lock held for the logger lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._file = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = None
        try:
            handle = self.path.open("a+b")
            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if handle is not None:
                handle.close()
            raise RuntimeError("Another Tokkun '99 logger instance is already running") from exc
        self._file = handle

    def release(self) -> None:
        if self._file is None:
            return
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None


def recover_partial_videos(data_root: Path) -> RecoveryResult:
    """Move abandoned FFmpeg partials to quarantine without deleting evidence."""
    root = data_root.resolve()
    videos = (root / "collection" / "videos").resolve()
    quarantine = (videos / "incomplete" / "recovered").resolve()
    recovered: list[Path] = []
    if not videos.exists():
        return RecoveryResult(())
    partials = {
        *videos.rglob("*.mp4.incomplete"),
        *videos.rglob("*.partial.mp4"),  # Recover files left by older versions.
    }
    for partial in sorted(partials):
        source = partial.resolve()
        if videos not in source.parents:
            raise ValueError(f"Partial video escaped data root: {source}")
        if source.parent == quarantine or quarantine in source.parents:
            continue
        quarantine.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
        if source.name.endswith(".mp4.incomplete"):
            stem = source.name.removesuffix(".mp4.incomplete")
        else:
            stem = source.name.removesuffix(".partial.mp4")
        target = quarantine / f"{stem}-{stamp}.recovered.mp4.incomplete"
        suffix = 1
        while target.exists():
            target = quarantine / (
                f"{stem}-{stamp}-{suffix}.recovered.mp4.incomplete"
            )
            suffix += 1
        os.replace(source, target)
        recovered.append(target)
    return RecoveryResult(tuple(recovered))


def ensure_disk_capacity(data_root: Path, *, minimum_free_bytes: int) -> None:
    if minimum_free_bytes < 0:
        raise ValueError("minimum_free_bytes must be non-negative")
    free = shutil.disk_usage(data_root.resolve()).free
    if free < minimum_free_bytes:
        raise OSError(
            f"Insufficient free disk space: {free / (1024**3):.2f} GiB free; "
            f"{minimum_free_bytes / (1024**3):.2f} GiB required"
        )


def discard_detached_video(storage: Storage, run_id: str, occurred_at: str) -> bool:
    """Detach a non-record video transactionally, then delete only that exact file."""
    relative = storage.detach_nonrecord_video(run_id, occurred_at)
    if relative is None:
        return False
    path = (storage.data_root / relative).resolve()
    videos = (storage.data_root / "collection" / "videos").resolve()
    if videos not in path.parents:
        raise ValueError(f"Refusing to delete outside video root: {path}")
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # The DB no longer claims this as a retained video. Leave the orphan for
        # explicit maintenance instead of risking a record reference.
        raise
    return True
