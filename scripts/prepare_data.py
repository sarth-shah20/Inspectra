"""Build a local pilot corpus and a reproducible aggregate audit."""

import argparse
import json
from collections import Counter
from itertools import islice
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from inspection_nlp.ingestion import load_source
from inspection_nlp.splits import assign_splits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/pilot"))
    parser.add_argument("--limit-per-file", type=int, default=250)
    parser.add_argument("--held-out-domain", choices=["construction", "aviation", "pipeline"])
    args = parser.parse_args()
    if args.limit_per_file < 1:
        parser.error("--limit-per-file must be positive; this command prepares a bounded pilot")
    if args.output.resolve().is_relative_to(args.raw.resolve()):
        parser.error("Output must be outside immutable raw storage")
    records, audits = [], []
    paths = sorted(p for p in args.raw.rglob("*") if p.suffix in {".xlsx", ".csv", ".txt"})
    if not paths:
        parser.error("No supported source files found")
    for path in paths:
        batch = list(islice(load_source(path), args.limit_per_file))
        records.extend(batch)
        audits.append(
            {
                "file": str(path.relative_to(args.raw)),
                "sample_rows": len(batch),
                "sha256": batch[0].source_sha256 if batch else None,
                "empty_narratives": sum(not r.clean_text for r in batch),
                "pii_flagged": sum(r.contains_sensitive_fields for r in batch),
            }
        )
    assign_splits(records, held_out_domain=args.held_out_domain)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "records.jsonl").open("w") as stream:
        for record in records:
            stream.write(record.model_dump_json() + "\n")
    # JSON payload preserves nested empty fields without Parquet null-struct ambiguity.
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "record_id": r.record_id,
                    "domain": r.domain,
                    "split": r.split,
                    "clean_text": r.clean_text,
                    "record_json": r.model_dump_json(),
                }
                for r in records
            ]
        ),
        args.output / "records.parquet",
    )
    audit = {
        "sampling": "first N rows per file; plumbing pilot, not evaluation sample",
        "seed": "inspectra-v1",
        "held_out_domain": args.held_out_domain,
        "rows": len(records),
        "domains": dict(Counter(r.domain for r in records)),
        "splits": dict(Counter(r.split for r in records)),
        "files": audits,
    }
    (args.output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
