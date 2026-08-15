"""Resource and writable-data path boundaries for development and packaging."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile

from .data_layout import DataLayout


DEFAULT_FFMPEG = Path(r"C:\tools\ffmpeg\bin\ffmpeg.exe")


@dataclass(frozen=True)
class AppPaths:
    resource_root: Path
    data_root: Path
    ffmpeg_path: Path = DEFAULT_FFMPEG

    @classmethod
    def for_development(
        cls, project_root: Path, *, ffmpeg_path: Path = DEFAULT_FFMPEG
    ) -> "AppPaths":
        root = project_root.resolve()
        return cls(root / "data" / "template", root / "data", ffmpeg_path)

    @classmethod
    def for_application(cls, project_root: Path) -> "AppPaths":
        """Resolve development or PyInstaller onedir paths without mixing writes/resources."""
        if getattr(sys, "frozen", False):
            bundle_root = Path(getattr(sys, "_MEIPASS")).resolve()
            executable_root = Path(sys.executable).resolve().parent
            return cls(
                resource_root=bundle_root / "template",
                data_root=executable_root / "data",
                ffmpeg_path=bundle_root / "ffmpeg.exe",
            )
        return cls.for_development(project_root)

    @property
    def layout(self) -> DataLayout:
        return DataLayout(self.data_root.resolve(), self.resource_root.resolve())

    def validate(self) -> None:
        layout = self.layout
        missing = [
            path
            for path in (layout.state_profile, layout.glyph_profile, self.ffmpeg_path.resolve())
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError("Required file not found: " + ", ".join(map(str, missing)))
        layout.log.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(dir=layout.log, prefix="write-test-", delete=True):
                pass
        except OSError as exc:
            raise OSError(f"Data directory is not writable: {layout.log}") from exc
