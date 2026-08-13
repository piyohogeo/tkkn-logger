from __future__ import annotations

import numpy as np

from scripts.collect_samples import change_score, save_png


def test_change_score_none_without_previous_frame() -> None:
    assert change_score(None, bytes([0, 0, 0, 255])) is None


def test_change_score_ignores_alpha_channel() -> None:
    before = bytes([10, 20, 30, 0])
    after = bytes([10, 20, 30, 255])

    assert change_score(before, after) == 0.0


def test_save_png_preserves_bgr_pixels(tmp_path) -> None:
    output = tmp_path / "pixel.png"

    save_png(output, bytes([10, 20, 30, 255]), width=1, height=1)

    restored = np.fromfile(output, dtype=np.uint8)
    image = __import__("cv2").imdecode(restored, __import__("cv2").IMREAD_COLOR)
    assert image.tolist() == [[[10, 20, 30]]]
