import json
import sqlite3
from pathlib import Path

from inspection_nlp.classification import load_source_splits


def test_source_splits_use_selected_train_and_group_representatives(tmp_path):
    snapshot = Path(tmp_path)
    connection = sqlite3.connect(snapshot / "index.sqlite")
    connection.execute(
        """CREATE TABLE records (record_id TEXT, domain TEXT, selected INTEGER, label TEXT,
        group_id TEXT, temporal TEXT, grouped TEXT, excluded TEXT)"""
    )
    connection.executemany(
        "INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
        [
            ("train", "aviation", 1, "cracked", "g1", "train", "train", ""),
            ("validation-a", "aviation", 0, "cracked", "g2", "validation", "validation", ""),
            ("validation-b", "aviation", 0, "cracked", "g2", "validation", "validation", ""),
            ("test", "aviation", 0, "cracked", "g3", "test", "test", ""),
            ("conflict-a", "aviation", 0, "cracked", "g4", "test", "test", ""),
            ("conflict-b", "aviation", 0, "failed", "g4", "test", "test", ""),
        ],
    )
    connection.commit()
    connection.close()
    records = [
        {"record_id": record_id, "clean_text": f"text {record_id}"}
        for record_id in (
            "train",
            "validation-a",
            "validation-b",
            "test",
            "conflict-a",
            "conflict-b",
        )
    ]
    (snapshot / "cleaned.jsonl").write_text("".join(json.dumps(row) + "\n" for row in records))
    splits = load_source_splits(
        snapshot, domain="aviation", split_column="temporal", labels=["cracked", "failed"]
    )
    assert [item.record_id for item in splits["train"]] == ["train"]
    assert [item.record_id for item in splits["validation"]] == ["validation-a"]
    assert [item.record_id for item in splits["test"]] == ["test"]
