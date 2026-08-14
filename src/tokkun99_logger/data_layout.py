"""Canonical separation of human collections, machine logs, and fixed templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataLayout:
    root: Path

    @property
    def collection(self) -> Path:
        return self.root / "collection"

    @property
    def messages(self) -> Path:
        return self.collection / "messages"

    @property
    def videos(self) -> Path:
        return self.collection / "videos"

    @property
    def runs(self) -> Path:
        return self.collection / "runs"

    @property
    def log(self) -> Path:
        return self.root / "log"

    @property
    def database(self) -> Path:
        return self.log / "logger.sqlite3"

    @property
    def lock(self) -> Path:
        return self.log / "logger.lock"

    @property
    def message_log(self) -> Path:
        return self.log / "messages"

    @property
    def regression(self) -> Path:
        return self.log / "regression"

    @property
    def template(self) -> Path:
        return self.root / "template"

    @property
    def state_profile(self) -> Path:
        return self.template / "states" / "v1" / "profile.json"

    @property
    def glyph_profile(self) -> Path:
        return self.template / "glyphs" / "v1" / "profile.json"
