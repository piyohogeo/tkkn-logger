from __future__ import annotations

import numpy as np

from tokkun99_logger.message_collector import MessageCollector, hamming_distance, normalize_message
from tokkun99_logger.storage import Storage


def message_frame(offset: int = 0) -> np.ndarray:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[50:55, 30 + offset : 80 + offset] = 255
    frame[80:90, 60 + offset : 65 + offset] = 255
    return frame


def test_message_normalization_crops_outer_whitespace() -> None:
    first = normalize_message(message_frame(0))
    shifted = normalize_message(message_frame(20))

    assert first.exact_hash == shifted.exact_hash
    assert first.mask.shape == shifted.mask.shape


def test_hamming_distance() -> None:
    assert hamming_distance("0000000000000000", "0000000000000001") == 1


def test_exact_message_reuses_cluster(tmp_path) -> None:
    storage = Storage(tmp_path / "data" / "logger.sqlite3", tmp_path / "data")
    storage.initialize()
    collector = MessageCollector(storage)

    first = collector.collect(message_frame(), "2026-08-13T10:00:00+09:00")
    second = collector.collect(message_frame(), "2026-08-13T10:01:00+09:00")

    assert first.is_new_cluster is True
    assert second.is_new_cluster is False
    assert first.cluster_id == second.cluster_id
    with storage.connect() as connection:
        cluster = connection.execute("SELECT * FROM message_clusters").fetchone()
        variant = connection.execute("SELECT * FROM message_variants").fetchone()
    assert cluster["observation_count"] == 2
    assert variant["observation_count"] == 2


def test_different_message_is_candidate_not_auto_merge(tmp_path) -> None:
    storage = Storage(tmp_path / "data" / "logger.sqlite3", tmp_path / "data")
    storage.initialize()
    collector = MessageCollector(storage)
    first = collector.collect(message_frame())
    changed = message_frame()
    changed[60:65, 100:120] = 255

    second = collector.collect(changed)

    assert second.is_new_cluster is True
    assert second.cluster_id != first.cluster_id
    assert second.nearest_cluster_id == first.cluster_id


def test_label_does_not_imply_human_verification(tmp_path) -> None:
    storage = Storage(tmp_path / "data" / "logger.sqlite3", tmp_path / "data")
    storage.initialize()
    collector = MessageCollector(storage)
    assignment = collector.collect(message_frame())

    collector.set_label(assignment.cluster_id, "仮ラベル", verified=False)

    with storage.connect() as connection:
        row = connection.execute(
            "SELECT label_text, is_verified FROM message_clusters WHERE message_cluster_id = ?",
            (assignment.cluster_id,),
        ).fetchone()
    assert (row["label_text"], row["is_verified"]) == ("仮ラベル", 0)
