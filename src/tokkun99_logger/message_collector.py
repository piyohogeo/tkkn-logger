"""Image-identity message collection with conservative clustering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np

from .result_reader import text_core_mask
from .storage import Storage


@dataclass(frozen=True)
class NormalizedMessage:
    mask: np.ndarray
    exact_hash: str
    perceptual_hash: str
    png: bytes


@dataclass(frozen=True)
class MessageAssignment:
    cluster_id: int
    exact_hash: str
    perceptual_hash: str
    is_new_cluster: bool
    nearest_cluster_id: int | None
    nearest_hamming_distance: int | None


def normalize_message(frame: np.ndarray) -> NormalizedMessage:
    mask = text_core_mask(frame)
    rows, columns = np.nonzero(mask)
    if len(rows) == 0:
        raise ValueError("Message frame contains no text core pixels")
    top, bottom = int(rows.min()), int(rows.max()) + 1
    left, right = int(columns.min()), int(columns.max()) + 1
    cropped = mask[top:bottom, left:right]
    packed = np.packbits(cropped, axis=None).tobytes()
    identity = cropped.shape[0].to_bytes(2, "big") + cropped.shape[1].to_bytes(2, "big") + packed
    exact_hash = hashlib.sha256(identity).hexdigest()
    visible = cropped.astype(np.uint8) * 255
    ok, encoded = cv2.imencode(".png", visible)
    if not ok:
        raise OSError("Could not encode normalized message PNG")
    small = cv2.resize(visible, (9, 8), interpolation=cv2.INTER_AREA)
    difference = small[:, 1:] > small[:, :-1]
    perceptual_hash = f"{int.from_bytes(np.packbits(difference).tobytes(), 'big'):016x}"
    return NormalizedMessage(cropped, exact_hash, perceptual_hash, encoded.tobytes())


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


class MessageCollector:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def collect(self, frame: np.ndarray, seen_at: str | None = None) -> MessageAssignment:
        normalized = normalize_message(frame)
        seen_at = seen_at or datetime.now().astimezone().isoformat()
        connection = self.storage.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT message_cluster_id FROM message_variants WHERE exact_hash = ?",
                (normalized.exact_hash,),
            ).fetchone()
            if existing is not None:
                cluster_id = int(existing["message_cluster_id"])
                connection.execute(
                    "UPDATE message_variants SET observation_count = observation_count + 1 WHERE exact_hash = ?",
                    (normalized.exact_hash,),
                )
                connection.execute(
                    """
                    UPDATE message_clusters
                    SET observation_count = observation_count + 1, last_seen_at = ?
                    WHERE message_cluster_id = ?
                    """,
                    (seen_at, cluster_id),
                )
                connection.commit()
                return MessageAssignment(
                    cluster_id,
                    normalized.exact_hash,
                    normalized.perceptual_hash,
                    False,
                    None,
                    None,
                )

            cluster_rows = connection.execute(
                "SELECT message_cluster_id, perceptual_hash FROM message_clusters WHERE merged_into IS NULL"
            ).fetchall()
            nearest_id: int | None = None
            nearest_distance: int | None = None
            for row in cluster_rows:
                if not row["perceptual_hash"]:
                    continue
                distance = hamming_distance(normalized.perceptual_hash, row["perceptual_hash"])
                if nearest_distance is None or distance < nearest_distance:
                    nearest_id = int(row["message_cluster_id"])
                    nearest_distance = distance

            relative_path = f"messages/clusters/{normalized.exact_hash}.png"
            final_path = self.storage.data_root / relative_path
            final_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = final_path.with_suffix(".partial.png")
            if final_path.exists() or temporary_path.exists():
                raise FileExistsError(final_path if final_path.exists() else temporary_path)
            temporary_path.write_bytes(normalized.png)
            candidate_note = None
            if nearest_id is not None:
                candidate_note = json.dumps(
                    {"candidate_cluster_id": nearest_id, "hamming_distance": nearest_distance}
                )
            cursor = connection.execute(
                """
                INSERT INTO message_clusters (
                    perceptual_hash, representative_path, notes,
                    first_seen_at, last_seen_at, observation_count
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (normalized.perceptual_hash, relative_path, candidate_note, seen_at, seen_at),
            )
            cluster_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO message_variants (
                    exact_hash, message_cluster_id, sample_path, observation_count
                ) VALUES (?, ?, ?, 1)
                """,
                (normalized.exact_hash, cluster_id, relative_path),
            )
            os.replace(temporary_path, final_path)
            connection.commit()
            return MessageAssignment(
                cluster_id,
                normalized.exact_hash,
                normalized.perceptual_hash,
                True,
                nearest_id,
                nearest_distance,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def set_label(self, cluster_id: int, label_text: str, *, verified: bool = False) -> None:
        if not label_text.strip():
            raise ValueError("label_text must not be empty")
        with self.storage.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE message_clusters
                SET label_text = ?, is_verified = ?
                WHERE message_cluster_id = ?
                """,
                (label_text, int(verified), cluster_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown message cluster: {cluster_id}")
