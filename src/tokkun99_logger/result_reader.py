"""Fixed-font RESULT reader with explicit unknown-glyph handling."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import json
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class GlyphMatch:
    label: str | None
    confidence: float
    runner_up_confidence: float


@dataclass(frozen=True)
class GlyphComponent:
    left: int
    right: int
    is_decimal: bool
    glyph: np.ndarray


@dataclass(frozen=True)
class ResultReading:
    survival_text: str | None
    survival_ms: int | None
    bullet_text: str | None
    bullet_count: int | None
    confidence: float
    unknown_glyphs: int
    needs_review: bool


@dataclass(frozen=True)
class ConsensusResult:
    reading: ResultReading | None
    agreeing_frames: int
    accepted_frames: int
    total_frames: int
    is_confirmed: bool


class ResultConsensus:
    def __init__(self, required_frames: int = 5) -> None:
        if required_frames < 1:
            raise ValueError("required_frames must be positive")
        self.required_frames = required_frames
        self.total_frames = 0
        self._readings: list[ResultReading] = []

    def add(self, reading: ResultReading) -> None:
        self.total_frames += 1
        if not reading.needs_review and reading.survival_ms is not None and reading.bullet_count is not None:
            self._readings.append(reading)

    def resolve(self) -> ConsensusResult:
        counts = Counter((reading.survival_ms, reading.bullet_count) for reading in self._readings)
        if not counts:
            return ConsensusResult(None, 0, 0, self.total_frames, False)
        (winner, agreeing_frames) = counts.most_common(1)[0]
        tied = sum(count == agreeing_frames for count in counts.values()) > 1
        representative = next(
            reading
            for reading in self._readings
            if (reading.survival_ms, reading.bullet_count) == winner
        )
        confirmed = agreeing_frames >= self.required_frames and not tied
        return ConsensusResult(
            reading=representative if confirmed else None,
            agreeing_frames=agreeing_frames,
            accepted_frames=len(self._readings),
            total_frames=self.total_frames,
            is_confirmed=confirmed,
        )


def text_core_mask(image: np.ndarray) -> np.ndarray:
    """Select neutral bright cores while rejecting saturated bullet colors."""
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("Expected a BGR image")
    bgr = image[:, :, :3]
    minimum = bgr.min(axis=2)
    spread = bgr.max(axis=2) - minimum
    return (minimum >= 160) & (spread <= 50)


def normalize_glyph(glyph: np.ndarray, size: tuple[int, int] = (12, 18)) -> np.ndarray:
    width, height = size
    glyph_height, glyph_width = glyph.shape
    if glyph_width > width or glyph_height > height:
        raise ValueError(f"Glyph {glyph.shape} does not fit canvas {(height, width)}")
    canvas = np.zeros((height, width), dtype=bool)
    left = (width - glyph_width) // 2
    bottom = height - 2
    top = bottom - glyph_height
    canvas[top:bottom, left : left + glyph_width] = glyph.astype(bool)
    return canvas


def extract_components(image: np.ndarray, allow_decimal: bool) -> list[GlyphComponent]:
    mask = text_core_mask(image).astype(np.uint8)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    components: list[GlyphComponent] = []
    for component in range(1, count):
        left, top, width, height, area = map(int, stats[component])
        is_digit = height >= 8 and area >= 10
        is_decimal = allow_decimal and width <= 3 and height <= 3 and area >= 3 and top >= image.shape[0] // 2
        if not (is_digit or is_decimal):
            continue
        glyph = labels[top : top + height, left : left + width] == component
        if width > 12 or height > 18:
            continue
        components.append(
            GlyphComponent(
                left=left,
                right=left + width,
                is_decimal=is_decimal,
                glyph=normalize_glyph(glyph),
            )
        )
    components.sort(key=lambda item: item.left)
    return components


def extract_glyphs(image: np.ndarray, allow_decimal: bool) -> list[np.ndarray]:
    return [component.glyph for component in extract_components(image, allow_decimal)]


def extract_digit_slot(image: np.ndarray, expected_left: int) -> np.ndarray | None:
    """Extract one digit from its fixed-width slot without joining neighboring text."""
    slot_left = expected_left - 1
    slot_right = expected_left + 7
    if slot_left < 0 or slot_right > image.shape[1]:
        return None
    mask = text_core_mask(image)[:, slot_left:slot_right].astype(np.uint8)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    candidates: list[np.ndarray] = []
    for component in range(1, count):
        left, top, width, height, area = map(int, stats[component])
        if height < 8 or area < 10:
            continue
        glyph = labels[top : top + height, left : left + width] == component
        if width <= 12 and height <= 16:
            candidates.append(normalize_glyph(glyph))
    return candidates[0] if len(candidates) == 1 else None


def has_decimal_at(image: np.ndarray, expected_left: int) -> bool:
    """Detect the geometric decimal marker independently of its antialiasing variant."""
    mask = text_core_mask(image)
    left = max(0, expected_left - 1)
    right = min(mask.shape[1], expected_left + 4)
    top = image.shape[0] // 2
    return np.count_nonzero(mask[top:, left:right]) >= 3


def select_survival_components(components: list[GlyphComponent]) -> list[GlyphComponent]:
    # The complete value is centered. Each extra integer digit moves its first
    # digit 4 px left and the decimal point 4 px right.
    decimal_indices = [index for index, component in enumerate(components) if component.is_decimal]
    candidates: list[list[GlyphComponent]] = []
    for decimal_index in decimal_indices:
        decimal = components[decimal_index]
        integer_digits = round((decimal.left - 55) / 4)
        if not 1 <= integer_digits <= 4 or abs(decimal.left - (55 + 4 * integer_digits)) > 2:
            continue
        before = components[max(0, decimal_index - integer_digits) : decimal_index]
        if len(before) != integer_digits or any(component.is_decimal for component in before):
            continue
        if any(
            right.left - left.right > 5
            for left, right in zip(before, [*before[1:], decimal])
        ):
            continue
        after: list[GlyphComponent] = []
        previous_right = decimal.right
        for component in components[decimal_index + 1 :]:
            if component.is_decimal:
                break
            if component.left - previous_right > 5:
                break
            after.append(component)
            previous_right = component.right
            if len(after) == 3:
                break
        expected_first = 53 - 4 * integer_digits
        centered_layout = (
            abs(before[0].left - expected_first) <= 2
        )
        if centered_layout and len(after) == 3:
            candidates.append([*before, decimal, *after])
    return candidates[0] if len(candidates) == 1 else []


def select_bullet_components(components: list[GlyphComponent]) -> list[GlyphComponent]:
    # The Japanese label ends before x=35 in this broad ROI. The suffix follows
    # the numeric run and is rejected later by glyph confidence.
    return [component for component in components if component.left >= 35 and not component.is_decimal]


def is_centered_digit_run(run: list[tuple[GlyphComponent, GlyphMatch]]) -> bool:
    """Accept one to four digits in the game's centered numeric field."""
    digit_count = len(run)
    if not 1 <= digit_count <= 4:
        return False
    expected_first = 53 - 4 * digit_count
    return abs(run[0][0].left - expected_first) <= 2


def dice(left: np.ndarray, right: np.ndarray) -> float:
    denominator = np.count_nonzero(left) + np.count_nonzero(right)
    if denominator == 0:
        return 1.0
    return float(2 * np.count_nonzero(left & right) / denominator)


def shifted_mask(mask: np.ndarray, horizontal: int, vertical: int) -> np.ndarray:
    """Translate a mask with zero fill and no wraparound."""
    shifted = np.zeros_like(mask)
    destination_y = slice(max(0, vertical), min(mask.shape[0], mask.shape[0] + vertical))
    destination_x = slice(max(0, horizontal), min(mask.shape[1], mask.shape[1] + horizontal))
    source_y = slice(max(0, -vertical), min(mask.shape[0], mask.shape[0] - vertical))
    source_x = slice(max(0, -horizontal), min(mask.shape[1], mask.shape[1] - horizontal))
    shifted[destination_y, destination_x] = mask[source_y, source_x]
    return shifted


def translation_tolerant_dice(left: np.ndarray, right: np.ndarray, maximum_shift: int) -> float:
    """Return the best Dice score after a small translation of the observed glyph."""
    if maximum_shift < 0:
        raise ValueError("maximum_shift must be non-negative")
    return max(
        dice(shifted_mask(left, horizontal, vertical), right)
        for vertical in range(-maximum_shift, maximum_shift + 1)
        for horizontal in range(-maximum_shift, maximum_shift + 1)
    )


class ResultReader:
    def __init__(self, profile_path: Path) -> None:
        profile_path = profile_path.resolve()
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.reference_size = tuple(profile["reference_size"])
        self.minimum_confidence = float(profile["minimum_confidence"])
        self.minimum_margin = float(profile["minimum_margin"])
        self.maximum_shift = int(profile.get("maximum_shift", 1))
        self.survival_roi = tuple(profile["rois"]["survival"])
        bullet_rois = profile["rois"]["bullets"]
        if bullet_rois and isinstance(bullet_rois[0], int):
            bullet_rois = [bullet_rois]
        self.bullet_rois = [tuple(roi) for roi in bullet_rois]
        self.rois = {"survival": self.survival_roi, "bullets": self.bullet_rois}
        self.templates: dict[str, list[np.ndarray]] = {}
        for label, paths in profile["templates"].items():
            variants = []
            for relative_path in paths:
                image = cv2.imread(str(profile_path.parent / relative_path), cv2.IMREAD_GRAYSCALE)
                if image is None:
                    raise FileNotFoundError(profile_path.parent / relative_path)
                variants.append(image.astype(bool))
            self.templates[label] = variants

    def match(self, glyph: np.ndarray) -> GlyphMatch:
        label_scores = sorted(
            (
                (
                    max(
                        translation_tolerant_dice(glyph, template, self.maximum_shift)
                        for template in variants
                    ),
                    label,
                )
                for label, variants in self.templates.items()
            ),
            reverse=True,
        )
        best_score, best_label = label_scores[0]
        runner_up = label_scores[1][0] if len(label_scores) > 1 else 0.0
        if best_score < self.minimum_confidence or best_score - runner_up < self.minimum_margin:
            return GlyphMatch(None, best_score, runner_up)
        return GlyphMatch(best_label, best_score, runner_up)

    @staticmethod
    def _roi_components(frame: np.ndarray, roi: tuple[int, int, int, int], allow_decimal: bool) -> list[GlyphComponent]:
        left, top, right, bottom = roi
        return extract_components(frame[top:bottom, left:right], allow_decimal=allow_decimal)

    @staticmethod
    def _roi_image(frame: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
        left, top, right, bottom = roi
        return frame[top:bottom, left:right]

    def _match_digit_slots(self, image: np.ndarray, positions: list[int]) -> list[GlyphMatch]:
        matches: list[GlyphMatch] = []
        for position in positions:
            glyph = extract_digit_slot(image, position)
            matches.append(GlyphMatch(None, 0.0, 0.0) if glyph is None else self.match(glyph))
        return matches

    def _read_survival(self, frame: np.ndarray) -> tuple[str | None, list[GlyphMatch]]:
        image = self._roi_image(frame, self.survival_roi)
        candidates: list[tuple[str, list[GlyphMatch]]] = []
        all_matches: list[GlyphMatch] = []
        for integer_digits in range(1, 5):
            first = 53 - 4 * integer_digits
            decimal = 55 + 4 * integer_digits
            if not has_decimal_at(image, decimal):
                continue
            integer_positions = [first + 8 * index for index in range(integer_digits)]
            fractional_positions = [decimal + 6 + 8 * index for index in range(3)]
            digit_matches = self._match_digit_slots(image, integer_positions + fractional_positions)
            matches = [*digit_matches[:integer_digits], GlyphMatch(".", 1.0, 0.0), *digit_matches[integer_digits:]]
            all_matches.extend(matches)
            if all(match.label is not None and match.label.isdigit() for match in digit_matches):
                candidates.append(("".join(match.label or "" for match in matches), matches))
        if len(candidates) != 1:
            return None, all_matches
        return candidates[0]

    def _read_bullets(self, frame: np.ndarray) -> tuple[str | None, list[GlyphMatch]]:
        candidates: list[tuple[str, list[GlyphMatch]]] = []
        all_matches: list[GlyphMatch] = []
        for roi in self.bullet_rois:
            image = self._roi_image(frame, roi)
            raw_components = extract_components(image, True)
            value_area = [component for component in raw_components if component.left >= 35]
            valid_decimal_positions = (59, 63, 67, 71)
            if any(
                component.is_decimal
                and any(abs(component.left - position) <= 2 for position in valid_decimal_positions)
                for component in value_area
            ):
                continue  # This is an auxiliary time row in the extended layout.
            for digit_count in range(1, 5):
                first = 53 - 4 * digit_count
                matches = self._match_digit_slots(
                    image, [first + 8 * index for index in range(digit_count)]
                )
                all_matches.extend(matches)
                if all(match.label is not None and match.label.isdigit() for match in matches):
                    candidates.append(("".join(match.label or "" for match in matches), matches))
        if len(candidates) != 1:
            return None, all_matches
        return candidates[0]

    def read(self, frame: np.ndarray) -> ResultReading:
        height, width = frame.shape[:2]
        if (width, height) != self.reference_size:
            raise ValueError(f"Expected {self.reference_size}, got {(width, height)}")
        survival_text, survival_matches = self._read_survival(frame)
        bullet_text, bullet_matches = self._read_bullets(frame)
        all_matches = survival_matches + bullet_matches
        unknown = sum(match.label is None for match in all_matches)
        confidence = min((match.confidence for match in all_matches), default=0.0)
        survival_ms: int | None = None
        bullet_count: int | None = None
        try:
            if survival_text is not None and survival_text.count(".") == 1:
                survival_ms = round(float(survival_text) * 1000)
            if bullet_text is not None and bullet_text.isdigit():
                bullet_count = int(bullet_text)
        except ValueError:
            survival_ms = None
            bullet_count = None
        needs_review = (
            unknown > 0
            or survival_ms is None
            or bullet_count is None
            or survival_ms < 0
            or bullet_count < 0
        )
        return ResultReading(
            survival_text=survival_text,
            survival_ms=survival_ms,
            bullet_text=bullet_text,
            bullet_count=bullet_count,
            confidence=confidence,
            unknown_glyphs=unknown,
            needs_review=needs_review,
        )
