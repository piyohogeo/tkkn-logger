"""Application entry point for the development GUI."""

from __future__ import annotations

from pathlib import Path

from .app_paths import AppPaths
from .gui import run_gui
from .logging_setup import configure_logging


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    paths = AppPaths.for_development(project_root)
    configure_logging(paths.layout.log)
    run_gui(paths)
    return 0
