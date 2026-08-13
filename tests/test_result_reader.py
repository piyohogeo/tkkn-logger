from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from tokkun99_logger.result_reader import (
    ResultConsensus,
    ResultReader,
    ResultReading,
    extract_glyphs,
    text_core_mask,
)


def test_text_core_mask_rejects_saturated_bullets() -> None:
    image = np.array([[[255, 255, 255], [0, 0, 255], [0, 255, 255]]], dtype=np.uint8)

    assert text_core_mask(image).tolist() == [[True, False, False]]


def test_extract_glyphs_orders_digit_decimal_digit() -> None:
    image = np.zeros((20, 16, 3), dtype=np.uint8)
    image[2:15, 1:4] = 255
    image[15:17, 7:9] = 255
    image[2:15, 12:16] = 255

    glyphs = extract_glyphs(image, allow_decimal=True)

    assert len(glyphs) == 3
    assert [int(np.count_nonzero(glyph)) for glyph in glyphs] == [39, 4, 52]


def test_local_golden_result_samples() -> None:
    project = Path(__file__).resolve().parents[1]
    profile = project / "data" / "templates" / "glyphs" / "v1" / "profile.json"
    frames = project / "artifacts" / "calibration" / "sessions" / "20260813T150904+0900" / "frames"
    if not profile.exists() or not frames.exists():
        pytest.skip("Local game calibration fixtures are intentionally not versioned")
    reader = ResultReader(profile)

    first = reader.read(cv2.imread(str(frames / "000233.png")))
    second = reader.read(cv2.imread(str(frames / "000842.png")))

    assert (first.survival_ms, first.bullet_count, first.needs_review) == (9408, 51, False)
    assert (second.survival_ms, second.bullet_count, second.needs_review) == (1024, 50, False)

    newer = project / "artifacts" / "calibration" / "sessions" / "20260813T151810+0900" / "frames"
    if newer.exists():
        expected = {
            210: (6448, 51),
            439: (7760, 52),
            675: (8064, 51),
            1008: (11792, 53),
        }
        for index, values in expected.items():
            reading = reader.read(cv2.imread(str(newer / f"{index:06d}.png")))
            assert (reading.survival_ms, reading.bullet_count) == values
            assert reading.needs_review is False


def test_local_live_smoke_result_samples() -> None:
    project = Path(__file__).resolve().parents[1]
    profile = project / "data" / "templates" / "glyphs" / "v1" / "profile.json"
    runs = project / "data" / "runs" / "2026" / "08" / "13"
    if not profile.exists() or not runs.exists():
        pytest.skip("Local live-smoke fixtures are intentionally not versioned")
    reader = ResultReader(profile)
    expected = {
        "731853da-1c8f-43a8-992c-1d943e25fe88": (6704, 51),
        "cbed2cb9-0e68-4114-840f-eac0954723ed": (6624, 52),
        "c874f176-609b-4082-88d3-59e764b416e1": (17376, 54),
        "f4948549-faaa-4c47-9a5b-454a1bdbd953": (37488, 56),
        "1be607b9-3fd5-41ac-b27e-d872598c342a": (8225, 52),
        "416bc679-e40d-45b6-8dd4-5a8e67f34420": (13047, 51),
    }
    for run_id, scores in expected.items():
        frame_path = runs / run_id / "result.png"
        frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        assert frame is not None, frame_path
        reading = reader.read(frame)
        assert reading.needs_review is False
        assert (reading.survival_ms, reading.bullet_count) == scores


def test_result_consensus_requires_five_agreeing_frames() -> None:
    reading = ResultReading("1.024", 1024, "50", 50, 1.0, 0, False)
    consensus = ResultConsensus(required_frames=5)
    for _ in range(4):
        consensus.add(reading)
    assert consensus.resolve().is_confirmed is False

    consensus.add(reading)
    resolved = consensus.resolve()
    assert resolved.is_confirmed is True
    assert resolved.reading == reading


def test_result_consensus_ignores_review_readings() -> None:
    valid = ResultReading("1.024", 1024, "50", 50, 1.0, 0, False)
    review = ResultReading(None, None, None, None, 0.5, 2, True)
    consensus = ResultConsensus(required_frames=2)
    consensus.add(valid)
    consensus.add(review)
    consensus.add(valid)

    resolved = consensus.resolve()
    assert resolved.is_confirmed is True
    assert resolved.accepted_frames == 2
    assert resolved.total_frames == 3
