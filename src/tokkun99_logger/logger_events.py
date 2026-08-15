"""Structured events emitted by the logger service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass(frozen=True)
class LoggerEvent:
    kind: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    data: dict[str, Any] = field(default_factory=dict)


EventSink = Callable[[LoggerEvent], None]
