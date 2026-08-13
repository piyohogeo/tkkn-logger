from __future__ import annotations

import cv2
import numpy as np

from tokkun99_logger.state_detector import (
    DebouncedStateDetector,
    GameState,
    StateClassifier,
    StateScores,
)


class FakeClassifier:
    def score(self, frame: np.ndarray) -> StateScores:
        marker = int(frame[0, 0])
        if marker == 1:
            return StateScores(title=1.0, result=0.0)
        if marker == 2:
            return StateScores(title=0.0, result=1.0)
        return StateScores(title=0.0, result=0.0)

    def anchor(self, scores: StateScores) -> GameState:
        if scores.title == 1.0:
            return GameState.TITLE
        if scores.result == 1.0:
            return GameState.RESULT
        return GameState.UNKNOWN


def frame(marker: int) -> np.ndarray:
    return np.full((1, 1), marker, dtype=np.uint8)


def test_debounced_detector_follows_expected_fsm() -> None:
    detector = DebouncedStateDetector(FakeClassifier(), stable_frames=3)  # type: ignore[arg-type]
    observed = []

    for marker in [1] * 3 + [0] * 3 + [2] * 3 + [0] * 3 + [1] * 3:
        result = detector.observe(frame(marker))
        if result.changed:
            observed.append(result.state)

    assert observed == [
        GameState.TITLE,
        GameState.PLAYING,
        GameState.RESULT,
        GameState.MESSAGE,
        GameState.TITLE,
    ]


def test_classifier_loads_binary_templates(tmp_path) -> None:
    cv2.imwrite(str(tmp_path / "title.png"), np.array([[255, 0]], dtype=np.uint8))
    cv2.imwrite(str(tmp_path / "result.png"), np.array([[0, 255]], dtype=np.uint8))
    (tmp_path / "profile.json").write_text(
        """{
          "reference_size": [2, 1],
          "text_threshold": 180,
          "title_threshold": 0.9,
          "result_threshold": 0.9,
          "templates": {
            "title": [{"roi": [0, 0, 2, 1], "path": "title.png"}],
            "result": [{"roi": [0, 0, 2, 1], "path": "result.png"}]
          }
        }""",
        encoding="utf-8",
    )
    classifier = StateClassifier(tmp_path / "profile.json")

    title_scores = classifier.score(np.array([[[255, 255, 255], [0, 0, 0]]], dtype=np.uint8))
    result_scores = classifier.score(np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8))

    assert classifier.anchor(title_scores) == GameState.TITLE
    assert classifier.anchor(result_scores) == GameState.RESULT
