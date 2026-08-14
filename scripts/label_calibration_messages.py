"""Apply reviewed-by-image provisional labels to the initial local catalog."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tokkun99_logger.message_collector import MessageCollector  # noqa: E402
from tokkun99_logger.storage import Storage  # noqa: E402


LABELS = {
    1: "顔も見たくない君を\nレーザーのレンズ磨き\nに任命する。活躍を期待する。",
    2: "何やってんだ?\nん?",
    3: "顔も見たくない君を\n使い捨ての駒\nに任命する。活躍を期待する。",
    4: "エンゲル係数高そうな君を\n弾拾い\nに任命する。活躍を期待する。",
}


def main() -> int:
    storage = Storage(PROJECT_ROOT / "data" / "log" / "logger.sqlite3", PROJECT_ROOT / "data")
    storage.initialize()
    collector = MessageCollector(storage)
    for cluster_id, label in LABELS.items():
        collector.set_label(cluster_id, label, verified=False)
    print(f"Applied {len(LABELS)} provisional labels; none marked human-verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
