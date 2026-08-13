"""Template-anchored, debounced state detection for the fixed 320x240 game."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

import cv2
import numpy as np


class GameState(str, Enum):
    UNKNOWN = "UNKNOWN"
    TITLE = "TITLE"
    PLAYING = "PLAYING"
    RESULT = "RESULT"
    MESSAGE = "MESSAGE"


@dataclass(frozen=True)
class StateScores:
    title: float
    result: float


@dataclass(frozen=True)
class Observation:
    state: GameState
    candidate: GameState
    candidate_frames: int
    scores: StateScores
    changed: bool


def _dice(left: np.ndarray, right: np.ndarray) -> float:
    left_bool = left.astype(bool)
    right_bool = right.astype(bool)
    denominator = np.count_nonzero(left_bool) + np.count_nonzero(right_bool)
    if denominator == 0:
        return 1.0
    intersection = np.count_nonzero(left_bool & right_bool)
    return float(2 * intersection / denominator)


def _text_mask(image: np.ndarray, threshold: int) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image >= threshold


class StateClassifier:
    def __init__(self, profile_path: Path) -> None:
        profile_path = profile_path.resolve()
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.profile_path = profile_path
        self.reference_size = tuple(profile["reference_size"])
        self.text_threshold = int(profile["text_threshold"])
        self.title_threshold = float(profile["title_threshold"])
        self.result_threshold = float(profile["result_threshold"])
        self.templates: dict[str, list[tuple[tuple[int, int, int, int], np.ndarray]]] = {}
        for state_name in ("title", "result"):
            entries: list[tuple[tuple[int, int, int, int], np.ndarray]] = []
            for item in profile["templates"][state_name]:
                roi = tuple(item["roi"])
                template_path = profile_path.parent / item["path"]
                template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
                if template is None:
                    raise FileNotFoundError(template_path)
                entries.append((roi, template.astype(bool)))
            self.templates[state_name] = entries

    def _score(self, state_name: str, frame: np.ndarray) -> float:
        scores: list[float] = []
        for (left, top, right, bottom), template in self.templates[state_name]:
            roi = frame[top:bottom, left:right]
            mask = _text_mask(roi, self.text_threshold)
            if mask.shape != template.shape:
                raise ValueError(f"Template shape mismatch for {state_name}: {mask.shape} != {template.shape}")
            scores.append(_dice(mask, template))
        return float(sum(scores) / len(scores))

    def score(self, frame: np.ndarray) -> StateScores:
        height, width = frame.shape[:2]
        if (width, height) != self.reference_size:
            raise ValueError(f"Expected {self.reference_size}, got {(width, height)}")
        return StateScores(title=self._score("title", frame), result=self._score("result", frame))

    def anchor(self, scores: StateScores) -> GameState:
        if scores.title >= self.title_threshold and scores.title > scores.result:
            return GameState.TITLE
        if scores.result >= self.result_threshold and scores.result > scores.title:
            return GameState.RESULT
        return GameState.UNKNOWN


class DebouncedStateDetector:
    """Apply the known user-driven FSM while retaining UNKNOWN at startup."""

    def __init__(self, classifier: StateClassifier, stable_frames: int = 3) -> None:
        if stable_frames < 1:
            raise ValueError("stable_frames must be positive")
        self.classifier = classifier
        self.stable_frames = stable_frames
        self.state = GameState.UNKNOWN
        self._candidate = GameState.UNKNOWN
        self._candidate_frames = 0

    def _next_candidate(self, anchor: GameState) -> GameState:
        if self.state == GameState.UNKNOWN:
            return anchor
        if self.state == GameState.TITLE:
            if anchor == GameState.TITLE:
                return GameState.TITLE
            if anchor == GameState.RESULT:
                return GameState.RESULT
            return GameState.PLAYING
        if self.state == GameState.PLAYING:
            if anchor == GameState.RESULT:
                return GameState.RESULT
            if anchor == GameState.TITLE:
                return GameState.TITLE
            return GameState.PLAYING
        if self.state == GameState.RESULT:
            if anchor == GameState.RESULT:
                return GameState.RESULT
            if anchor == GameState.TITLE:
                return GameState.TITLE
            return GameState.MESSAGE
        if self.state == GameState.MESSAGE:
            return GameState.TITLE if anchor == GameState.TITLE else GameState.MESSAGE
        return GameState.UNKNOWN

    def observe(self, frame: np.ndarray) -> Observation:
        scores = self.classifier.score(frame)
        candidate = self._next_candidate(self.classifier.anchor(scores))
        if candidate == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate = candidate
            self._candidate_frames = 1
        changed = False
        if candidate != GameState.UNKNOWN and self._candidate_frames >= self.stable_frames and candidate != self.state:
            self.state = candidate
            changed = True
        return Observation(
            state=self.state,
            candidate=candidate,
            candidate_frames=self._candidate_frames,
            scores=scores,
            changed=changed,
        )
