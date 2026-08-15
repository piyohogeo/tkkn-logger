"""Development launcher for the Tkinter GUI."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
