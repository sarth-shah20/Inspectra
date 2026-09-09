"""Export a privacy-gated, deterministic stratified annotation candidate batch."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from inspection_nlp.data_quality import fingerprint


def allocate(strata: dict[tuple[str, str], list[dict]], per_domain: int) -> set[str]:
    """Allocate a deterministic near-equal number of candidates to every available stratum."""
    selected = set()
    by_domain: dict[str, list[tuple[tuple[str, str], list[dict]]]] = defaultdict(list)
    for key, rows in strata.items():
        by_domain[key[0]].append((key, rows))
    for domain, groups in by_domain.items():
        del domain
        ordered = sorted(groups, key=lambda item: item[0][1])
        quota, remainder = divmod(per_domain, len(ordered))
        for index, (_, rows) in enumerate(ordered):
            selected.update(
                row["record_id"]
                for row in sorted(rows, key=lambda row: row["rank"])[
                    : quota + int(index < remainder)
                ]
            )
    return selected


def candidates(snapshot: Path, per_domain: int) -> list[dict]:
    connection = sqlite3.connect(f"file:{(snapshot / 'index.sqlite').resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """WITH conflicts AS (
                SELECT group_id, domain FROM records WHERE label!=''
                GROUP BY group_id, domain HAVING COUNT(DISTINCT label)>1
            ), representatives AS (
                SELECT r.domain, r.label, r.record_id, r.group_id,
                    ROW_NUMBER() OVER (PARTITION BY r.group_id, r.domain ORDER BY r.sample_rank) AS row_rank
                FROM records r LEFT JOIN conflicts c ON c.group_id=r.group_id AND c.domain=r.domain
                WHERE r.excluded='' AND r.label!='' AND c.group_id IS NULL
                  AND ((r.domain='construction' AND r.official_safe='train')
                    OR (r.domain='aviation' AND r.temporal='train')
                    OR (r.domain='pipeline' AND r.grouped='train'))
            ) SELECT domain, label, record_id, group_id FROM representatives WHERE row_rank=1"""
        ).fetchall()
    finally:
        connection.close()
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for domain, label, record_id, group_id in rows:
        strata[(domain, label)].append(
            {
                "record_id": record_id,
                "domain": domain,
                "source_label": label,
                "group_id": group_id,
                "rank": fingerprint("annotation-v1:" + record_id),
            }
        )
    selected = allocate(strata, per_domain)
    candidates = [row for rows in strata.values() for row in rows if row["record_id"] in selected]
    return sorted(candidates, key=lambda row: (row["domain"], row["source_label"], row["rank"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/processed/corpus-v1"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/annotations/pilot_candidates.jsonl")
    )
    parser.add_argument("--per-domain", type=int, default=90)
    parser.add_argument("--privacy-reviewed-record-ids", type=Path)
    args = parser.parse_args()
    if args.per_domain < 1:
        parser.error("--per-domain must be positive")
    if not args.privacy_reviewed_record_ids:
        parser.error("Refusing to export narrative text without --privacy-reviewed-record-ids")
    approved = {line.strip() for line in args.privacy_reviewed_record_ids.open() if line.strip()}
    chosen = candidates(args.snapshot, args.per_domain)
    missing = [row["record_id"] for row in chosen if row["record_id"] not in approved]
    if missing:
        parser.error(f"{len(missing)} selected records have not passed privacy review")
    text = {}
    with (args.snapshot / "cleaned.jsonl").open() as source:
        for line in source:
            record = json.loads(line)
            if record["record_id"] in approved:
                text[record["record_id"]] = record["display_text"]
    if len(text) < len(chosen):
        parser.error("A privacy-reviewed record is absent from the frozen snapshot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as target:
        for row in chosen:
            target.write(
                json.dumps(
                    {
                        "record_id": row["record_id"],
                        "domain": row["domain"],
                        "source_label": row["source_label"],
                        "group_id": row["group_id"],
                        "text": text[row["record_id"]],
                        "label_origin": "source_candidate",
                        "annotation_status": "unannotated",
                    }
                )
                + "\n"
            )
    print(json.dumps({"records": len(chosen), "output": str(args.output)}))


if __name__ == "__main__":
    main()
