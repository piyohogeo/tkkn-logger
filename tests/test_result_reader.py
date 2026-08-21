from __future__ import annotations

from pathlib import Path
import sqlite3

import cv2
import numpy as np
import pytest

from tokkun99_logger.result_reader import (
    ResultConsensus,
    ResultReader,
    ResultReading,
    GlyphComponent,
    GlyphMatch,
    extract_glyphs,
    extract_digit_slot,
    has_decimal_at,
    is_auxiliary_time_row,
    is_centered_digit_run,
    normalize_glyph,
    select_survival_components,
    text_core_mask,
    translation_tolerant_dice,
)


def test_text_core_mask_rejects_saturated_bullets() -> None:
    image = np.array([[[255, 255, 255], [0, 0, 255], [0, 255, 255]]], dtype=np.uint8)

    assert text_core_mask(image).tolist() == [[True, False, False]]


def test_translation_tolerant_dice_recovers_one_pixel_alignment_error() -> None:
    template = np.zeros((6, 6), dtype=bool)
    template[2:5, 2:4] = True
    observed = np.zeros_like(template)
    observed[1:4, 2:4] = True

    assert translation_tolerant_dice(observed, template, 0) < 1.0
    assert translation_tolerant_dice(observed, template, 1) == 1.0


def test_extract_glyphs_orders_digit_decimal_digit() -> None:
    image = np.zeros((20, 16, 3), dtype=np.uint8)
    image[2:15, 1:4] = 255
    image[15:17, 7:9] = 255
    image[2:15, 12:16] = 255

    glyphs = extract_glyphs(image, allow_decimal=True)

    assert len(glyphs) == 3
    assert [int(np.count_nonzero(glyph)) for glyph in glyphs] == [39, 4, 52]


@pytest.mark.parametrize(
    ("glyph_height", "expected_bottom_padding"),
    [(13, 2), (16, 2), (17, 1), (18, 0)],
)
def test_normalize_glyph_reduces_bottom_padding_for_tall_components(
    glyph_height: int, expected_bottom_padding: int
) -> None:
    glyph = np.ones((glyph_height, 10), dtype=bool)

    normalized = normalize_glyph(glyph)

    assert normalized.shape == (18, 12)
    assert np.count_nonzero(normalized) == glyph_height * 10
    if expected_bottom_padding:
        assert not normalized[-expected_bottom_padding:].any()


def test_normalize_glyph_rejects_component_taller_than_canvas() -> None:
    with pytest.raises(ValueError, match="does not fit canvas"):
        normalize_glyph(np.ones((19, 10), dtype=bool))


def test_digit_slot_separates_digit_from_touching_suffix() -> None:
    image = np.zeros((20, 24, 3), dtype=np.uint8)
    image[3:16, 5:12] = 255
    image[8:12, 12:18] = 255  # Touching suffix outside the numeric slot.

    glyph = extract_digit_slot(image, expected_left=5)

    assert glyph is not None
    assert np.count_nonzero(glyph) == 13 * 7


def test_decimal_detection_uses_geometry_not_exact_shape() -> None:
    image = np.zeros((20, 20, 3), dtype=np.uint8)
    image[15:17, 8:10] = 255
    assert has_decimal_at(image, 8)
    image[:] = 0
    image[15, 7:10] = 255
    assert has_decimal_at(image, 8)


def component(left: int, *, decimal: bool = False) -> GlyphComponent:
    return GlyphComponent(left, left + (2 if decimal else 6), decimal, np.zeros((18, 12), bool))


@pytest.mark.parametrize(
    ("digits", "first_left", "decimal_left"),
    [(1, 49, 59), (2, 45, 63), (3, 41, 67), (4, 37, 71)],
)
def test_survival_layout_accepts_one_to_four_integer_digits(
    digits: int, first_left: int, decimal_left: int
) -> None:
    integer = [component(first_left + 8 * index) for index in range(digits)]
    fractional = [component(decimal_left + 6 + 8 * index) for index in range(3)]

    selected = select_survival_components([*integer, component(decimal_left, decimal=True), *fractional])

    assert len(selected) == digits + 4


def test_bullet_suffix_dot_is_not_an_auxiliary_time_row() -> None:
    components = [component(45), component(53), component(66, decimal=True)]

    assert not is_auxiliary_time_row(components)


def test_complete_centered_time_is_an_auxiliary_time_row() -> None:
    components = [
        component(49),
        component(59, decimal=True),
        component(65),
        component(73),
        component(81),
    ]

    assert is_auxiliary_time_row(components)


@pytest.mark.parametrize("digits", [1, 2, 3, 4])
def test_bullet_layout_accepts_one_to_four_centered_digits(digits: int) -> None:
    first_left = 53 - 4 * digits
    run = [
        (component(first_left + 8 * index), GlyphMatch(str(index), 1.0, 0.0))
        for index in range(digits)
    ]

    assert is_centered_digit_run(run)


def test_centered_digit_run_rejects_five_digits_and_wrong_anchor() -> None:
    match = GlyphMatch("1", 1.0, 0.0)
    assert not is_centered_digit_run([(component(45), match)])
    assert not is_centered_digit_run([(component(33 + 8 * index), match) for index in range(5)])


def test_local_golden_result_samples() -> None:
    project = Path(__file__).resolve().parents[1]
    profile = project / "data" / "template" / "glyphs" / "v1" / "profile.json"
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
    profile = project / "data" / "template" / "glyphs" / "v1" / "profile.json"
    database = project / "data" / "log" / "logger.sqlite3"
    if not profile.exists() or not database.exists():
        pytest.skip("Local live-smoke fixtures are intentionally not versioned")
    reader = ResultReader(profile)
    expected = {
        "731853da-1c8f-43a8-992c-1d943e25fe88": (6704, 51),
        "cbed2cb9-0e68-4114-840f-eac0954723ed": (6624, 52),
        "c874f176-609b-4082-88d3-59e764b416e1": (17376, 54),
        "f4948549-faaa-4c47-9a5b-454a1bdbd953": (37488, 56),
        "1be607b9-3fd5-41ac-b27e-d872598c342a": (8225, 52),
        "416bc679-e40d-45b6-8dd4-5a8e67f34420": (13047, 51),
        # Three-row RESULT layout: the lower auxiliary metric must not become
        # a second bullet candidate, and a leading bullet digit cannot vanish.
        "64ce470d-2412-4a52-8a06-f937c9b40ff1": (41968, 60),
        "a88d9184-5c9a-44f1-8b5c-125bb2bda1d9": (21360, 56),
    }
    with sqlite3.connect(database) as connection:
        for run_id, scores in expected.items():
            row = connection.execute(
                "SELECT result_frame_path FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None or not row[0]:
                pytest.skip("Local live-smoke fixtures are intentionally not versioned")
            frame_path = project / "data" / row[0]
            if not frame_path.is_file():
                pytest.skip("Local live-smoke fixtures are intentionally not versioned")
            frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
            assert frame is not None, frame_path
            reading = reader.read(frame)
            assert reading.needs_review is False
            assert (reading.survival_ms, reading.bullet_count) == scores


def test_result_consensus_honors_configured_agreement_count() -> None:
    reading = ResultReading("1.024", 1024, "50", 50, 1.0, 0, False)
    consensus = ResultConsensus(required_frames=5)
    for _ in range(4):
        consensus.add(reading)
    assert consensus.resolve().is_confirmed is False

    consensus.add(reading)
    resolved = consensus.resolve()
    assert resolved.is_confirmed is True
    assert resolved.reading == reading


def test_result_consensus_can_confirm_one_valid_frame_after_state_debounce() -> None:
    reading = ResultReading("1.024", 1024, "50", 50, 1.0, 0, False)
    consensus = ResultConsensus(required_frames=1)

    consensus.add(reading)

    resolved = consensus.resolve()
    assert resolved.is_confirmed is True
    assert resolved.agreeing_frames == 1
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
