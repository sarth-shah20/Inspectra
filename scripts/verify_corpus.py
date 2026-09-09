"""Verify snapshot hashes, canonical rows, sample membership, and frozen assignments."""

import argparse
import json
import sqlite3
from pathlib import Path

import pyarrow.parquet as pq

from inspection_nlp.ingestion import checksum
from inspection_nlp.schemas import Record


def verify(snapshot: Path, raw: Path) -> dict:
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if manifest["status"] != "frozen":
        raise ValueError("Snapshot is not frozen")
    for name, digest in manifest["artifacts"].items():
        if checksum(snapshot / name) != digest:
            raise ValueError(f"Artifact checksum mismatch: {name}")
    for source in manifest["sources"]:
        if checksum(raw / source["path"]) != source["sha256"]:
            raise ValueError(f"Raw source changed: {source['path']}")
    connection = sqlite3.connect(f"file:{snapshot.resolve() / 'index.sqlite'}?mode=ro", uri=True)
    expected = connection.execute("""SELECT r.record_id,r.group_id,r.domain,r.grouped,r.temporal,
        r.official,r.official_safe,r.selected,r.excluded,g.domains FROM records r
        JOIN groups g ON r.group_id=g.group_id ORDER BY r.idx""")
    count = 0
    for batch in pq.ParquetFile(snapshot / "assignments.parquet").iter_batches(batch_size=5000):
        for actual in batch.to_pylist():
            row = next(expected, None)
            if row is None:
                raise ValueError("Unexpected assignment row")
            keys = [
                "record_id",
                "group_id",
                "domain",
                "grouped_split",
                "faa_temporal_split",
                "fire_door_official_split",
                "fire_door_safe_split",
                "selected_for_training",
                "exclusion_reason",
            ]
            if [actual[k] for k in keys] != [*row[:7], bool(row[7]), row[8]]:
                raise ValueError("Assignment disagrees with snapshot index")
            for domain in ("construction", "aviation", "pipeline"):
                split = (
                    row[3]
                    if row[3] in {"demo", "excluded"}
                    else (
                        "test"
                        if domain in row[9].split(",")
                        else "train"
                        if row[3] == "train"
                        else "validation"
                    )
                )
                if actual[f"holdout_{domain}"] != split:
                    raise ValueError("Held-out-domain assignment mismatch")
            count += 1
    if next(expected, None) is not None or count != manifest["rows"]:
        raise ValueError("Assignment count mismatch")
    for column in ("grouped", "temporal", "official_safe"):
        collisions = connection.execute(f"""SELECT COUNT(*) FROM (
            SELECT group_id FROM records WHERE {column} IN ('train','validation','test')
            GROUP BY group_id HAVING COUNT(DISTINCT {column})>1)""").fetchone()[0]
        if collisions:
            raise ValueError(f"Leakage in {column}")
    canonical_count = 0
    with (snapshot / "cleaned.jsonl").open() as source:
        for batch in pq.ParquetFile(snapshot / "cleaned.parquet").iter_batches(batch_size=5000):
            for row in batch.to_pylist():
                line = next(source, None)
                if line is None or line.strip() != row["record_json"]:
                    raise ValueError("JSONL/Parquet payload mismatch")
                record = Record.model_validate_json(line)
                if record.record_id != row["record_id"] or record.clean_text != row["clean_text"]:
                    raise ValueError("Canonical scalar mismatch")
                canonical_count += 1
        if next(source, None) is not None or canonical_count != count:
            raise ValueError("Canonical record count mismatch")
    selected = {
        r[0]: r[1]
        for r in connection.execute("SELECT record_id,domain FROM records WHERE selected=1")
    }
    samples = 0
    for line in (snapshot / "training_sample.jsonl").open():
        record = Record.model_validate_json(line)
        if selected.pop(record.record_id, None) != record.domain or record.split != "train":
            raise ValueError("Unexpected, repeated, or incorrectly assigned training sample")
        samples += 1
    if selected:
        raise ValueError("Missing training samples")
    connection.close()
    return {
        "status": "passed",
        "canonical_rows": count,
        "training_sample_rows": samples,
        "checks": [
            "raw checksums",
            "frozen artifact checksums",
            "all assignment policies",
            "group isolation",
            "full canonical JSONL/Parquet round-trip",
            "training membership",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/processed/corpus-v1"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot, args.raw), indent=2))


if __name__ == "__main__":
    main()
