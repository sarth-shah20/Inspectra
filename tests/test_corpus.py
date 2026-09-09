import csv
import json
import runpy
import sqlite3

import pyarrow.parquet as pq
import pytest
from openpyxl import Workbook

from inspection_nlp.data_quality import faa_period, text_keys
from inspection_nlp.ingestion import checksum

pipeline = runpy.run_path("scripts/prepare_corpus.py")


def write_csv(path, records):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def test_template_keys():
    left = "The valve was inspected and a 10 mm gap was observed."
    right = "THE valve was inspected, and a 12 mm gap was observed!"
    assert text_keys(left)[0] != text_keys(right)[0]
    assert text_keys(left)[1] == text_keys(right)[1]
    assert text_keys("10 mm gap")[1] is None
    assert text_keys("No crack found")[0] != text_keys("Crack found")[0]


def test_full_pipeline_temporal_official_and_freeze(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "output"
    raw.mkdir()
    output.mkdir()
    for year, narratives in [
        (2023, ["Repeated leak report", "Cracked actuator", "Pump corroded", "Same door defect"]),
        (2024, ["Different valve failure"]),
        (2025, ["Repeated leak report", "Broken fitting"]),
        (2026, ["Demo failure only"]),
    ]:
        write_csv(
            raw / f"SDR-{year}.csv",
            [
                {
                    "OperatorControlNumber": f"{year}-{i}",
                    "Discrepancy": text,
                    "PartCondition": "failed",
                }
                for i, text in enumerate(narratives)
            ],
        )
    for split in ["training", "test"]:
        workbook = Workbook()
        workbook.active.append(["Apartments", "English", "Classification_English"])
        workbook.active.append(["A", "Same door defect", "dent"])
        if split == "training":
            workbook.active.append(["B", None, "scratch"])
        workbook.save(raw / f"{split}.xlsx")
    db = sqlite3.connect(output / "index.sqlite")
    sources, size = pipeline["index_corpus"](raw, output, db)
    duplicates = pipeline["group_and_split"](db, size, "fixed")
    assert duplicates["exact"] == 3
    pipeline["select_training_sample"](db, 1)
    pipeline["validate"](db)
    assert db.execute(
        "SELECT DISTINCT temporal FROM records WHERE exact=(SELECT exact FROM records "
        "WHERE record_id LIKE 'faa%' AND year=2023 LIMIT 1)"
    ).fetchall() == [("quarantine",)]
    assert db.execute(
        "SELECT DISTINCT official_safe FROM records WHERE domain='construction' AND excluded=''"
    ).fetchall() == [("quarantine",)]
    assert db.execute("SELECT COUNT(*) FROM records WHERE selected=1").fetchone()[0] == 1
    assert db.execute("SELECT grouped FROM records WHERE year=2026").fetchone()[0] == "demo"
    assert (
        db.execute("SELECT excluded FROM records WHERE excluded!=''").fetchone()[0]
        == "empty_narrative"
    )
    pipeline["export_frozen"](db, output)
    assert pq.read_table(output / "cleaned.parquet").num_rows == size
    assignments = pq.read_table(output / "assignments.parquet").to_pylist()
    assert len(assignments) == size
    shared_group = db.execute(
        "SELECT group_id FROM records WHERE domain='construction' AND excluded='' LIMIT 1"
    ).fetchone()[0]
    shared = [r for r in assignments if r["group_id"] == shared_group]
    assert {r["domain"] for r in shared} == {"aviation", "construction"}
    assert {r["holdout_construction"] for r in shared} == {"test"}
    assert {r["holdout_aviation"] for r in shared} == {"test"}
    selected = [json.loads(line) for line in (output / "training_sample.jsonl").open()]
    assert len(selected) == 1
    report = pipeline["audit"](db, duplicates)
    assert len(report["text_lengths"]) == 2
    artifacts = {
        p.name: checksum(p) for p in output.iterdir() if p.suffix in {".jsonl", ".parquet"}
    }
    (output / "manifest.json").write_text(
        json.dumps({"status": "frozen", "sources": sources, "artifacts": artifacts, "rows": size})
    )
    db.close()
    verifier = runpy.run_path("scripts/verify_corpus.py")["verify"]
    assert verifier(output, raw)["canonical_rows"] == size
    with (output / "training_sample.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verifier(output, raw)


def test_period_policy():
    assert [faa_period(y) for y in (2023, 2024, 2025, 2026, 2027)] == [
        "train",
        "validation",
        "test",
        "demo",
        "quarantine",
    ]


def test_conflicting_labels_excluded_from_training(tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "output"
    raw.mkdir()
    output.mkdir()
    write_csv(
        raw / "SDR-2023.csv",
        [
            {
                "OperatorControlNumber": "a",
                "Discrepancy": "Same component condition",
                "PartCondition": "failed",
            },
            {
                "OperatorControlNumber": "b",
                "Discrepancy": "Same component condition",
                "PartCondition": "corroded",
            },
            {
                "OperatorControlNumber": "c",
                "Discrepancy": "Independent pump leak",
                "PartCondition": "leaking",
            },
        ],
    )
    db = sqlite3.connect(":memory:")
    _, size = pipeline["index_corpus"](raw, output, db)
    pipeline["group_and_split"](db, size, "fixed")
    pipeline["select_training_sample"](db, 75000)
    assert db.execute("SELECT label FROM records WHERE selected=1").fetchall() == [("leaking",)]
    db.close()


def test_refuses_existing_snapshot(tmp_path, monkeypatch):
    snapshot = tmp_path / "frozen"
    snapshot.mkdir()
    sentinel = snapshot / "manifest.json"
    sentinel.write_text("original")
    monkeypatch.setattr("sys.argv", ["prepare_corpus.py", "--output", str(snapshot)])
    with pytest.raises(SystemExit):
        pipeline["main"]()
    assert sentinel.read_text() == "original"
