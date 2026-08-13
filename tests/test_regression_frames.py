from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from tokkun99_logger.regression_frames import RegressionFrameLogger


def test_regression_frame_logger_writes_distinct_lossless_pngs(tmp_path) -> None:
    logger = RegressionFrameLogger(tmp_path, maximum_frames=2)
    logger.start("run-1", "2026-08-13T15:09:04+09:00")
    first = np.zeros((4, 5, 3), dtype=np.uint8)
    second = first.copy()
    second[2, 3] = (1, 2, 3)
    third = first.copy()
    third[1, 1] = 255

    first_path = logger.add(first)
    assert logger.add(first.copy()) is None
    second_path = logger.add(second)
    assert logger.add(third) is None
    assert first_path is not None and second_path is not None
    assert np.array_equal(cv2.imread(str(first_path)), first)
    assert np.array_equal(cv2.imread(str(second_path)), second)

    assert logger.finalize(status="complete", survival_ms=1024, bullet_count=50) == 2
    manifest = json.loads((first_path.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lossless"] is True
    assert manifest["saved_frames"] == 2
    assert manifest["duplicate_frames"] == 1
    assert manifest["dropped_frames"] == 1


def test_regression_frame_logger_requires_active_run(tmp_path) -> None:
    logger = RegressionFrameLogger(tmp_path)
    with pytest.raises(RuntimeError):
        logger.add(np.zeros((1, 1, 3), dtype=np.uint8))
