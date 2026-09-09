"""Immutable full-corpus cleaning, grouping, and frozen experiment manifests.

Uses a local SQLite index and batched Parquet to avoid loading narratives into RAM.
Outputs contain sensitive source metadata and are not approved for redistribution.
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from inspection_nlp.data_quality import (
    POLICY_VERSION,
    UnionFind,
    faa_period,
    fingerprint,
    grouped_split,
    text_keys,
)
from inspection_nlp.ingestion import checksum, load_source
from inspection_nlp.schemas import Record


def index_corpus(raw, output, connection):
    connection.execute("""CREATE TABLE records (
        idx INTEGER PRIMARY KEY, record_id TEXT UNIQUE, event TEXT, exact TEXT, template TEXT,
        domain TEXT, year INTEGER, label TEXT, subset TEXT, words INTEGER, pii INTEGER,
        excluded TEXT, official TEXT, group_id TEXT, grouped TEXT, temporal TEXT,
        official_safe TEXT, sample_rank TEXT, selected INTEGER DEFAULT 0)""")
    paths = sorted(p for p in raw.rglob("*") if p.suffix in {".xlsx", ".csv", ".txt"})
    if not paths:
        raise ValueError("No supported source files found")
    manifest, index = [], 0
    with (output / "cleaned.jsonl").open("w") as target:
        for path in paths:
            count = 0
            for record in load_source(path):
                exact, template = text_keys(record.clean_text)
                metadata = record.document_metadata
                metadata["cleaning_version"] = POLICY_VERSION
                year_match = re.search(r"SDR-(\d{4})", path.stem)
                year = int(year_match[1]) if year_match else 0
                label_field = {
                    "construction": "Classification_English",
                    "aviation": "PartCondition",
                    "pipeline": "CAUSE",
                }[record.domain]
                label = record.structured_source_fields.get(label_field, "").strip().casefold()
                official = {"training": "train", "validation": "validation", "test": "test"}.get(
                    metadata.get("original_split", ""), ""
                )
                excluded = metadata.get("exclusion_reason", "")
                if not re.search(r"[a-zA-Z]", record.clean_text.replace("[REDACTED]", "")):
                    excluded = excluded or "no_alphabetic_narrative"
                metadata["training_eligibility"] = "excluded" if excluded else "candidate"
                if excluded:
                    metadata["exclusion_reason"] = excluded
                target.write(record.model_dump_json() + "\n")
                connection.execute(
                    """INSERT INTO records (
                    idx,record_id,event,exact,template,domain,year,label,subset,words,pii,
                    excluded,official,sample_rank) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        index,
                        record.record_id,
                        record.source_event_id,
                        exact,
                        template,
                        record.domain,
                        year,
                        label,
                        path.stem,
                        len(record.clean_text.split()),
                        int(record.contains_sensitive_fields),
                        excluded,
                        official,
                        fingerprint("sample-v1:" + record.record_id),
                    ),
                )
                index += 1
                count += 1
            connection.commit()
            manifest.append(
                {"path": str(path.relative_to(raw)), "sha256": checksum(path), "rows": count}
            )
            print(f"Cleaned {path.name}: {count} rows", flush=True)
    return manifest, index


def group_and_split(connection, size, seed):
    union = UnionFind(size)
    duplicate_counts = {}
    for column in ("event", "exact", "template"):
        connection.execute(f"CREATE INDEX idx_{column} ON records({column})")
        previous, first, links = None, None, 0
        for index, key in connection.execute(
            f"SELECT idx,{column} FROM records WHERE {column} IS NOT NULL "
            f"AND {column} != '' ORDER BY {column},idx"
        ):
            if key == previous:
                union.union(first, index)
                links += 1
            else:
                previous, first = key, index
        duplicate_counts[column] = links
    connection.execute("CREATE TABLE membership(idx INTEGER PRIMARY KEY, root INTEGER)")
    connection.executemany(
        "INSERT INTO membership VALUES (?,?)", ((i, union.root(i)) for i in range(size))
    )
    connection.execute("CREATE INDEX idx_root ON membership(root)")
    connection.execute("""CREATE TABLE groups AS SELECT m.root, MIN(r.record_id) AS group_id,
        COUNT(*) AS members, GROUP_CONCAT(DISTINCT r.domain) AS domains
        FROM records r JOIN membership m USING(idx) GROUP BY m.root""")
    connection.execute("CREATE UNIQUE INDEX group_root ON groups(root)")
    connection.execute("CREATE UNIQUE INDEX group_name ON groups(group_id)")
    connection.execute("""UPDATE records SET group_id=(SELECT g.group_id FROM membership m
        JOIN groups g USING(root) WHERE m.idx=records.idx)""")
    connection.execute("CREATE INDEX idx_group_id ON records(group_id)")
    for group_id, years, officials in connection.execute("""SELECT group_id,
        GROUP_CONCAT(DISTINCT CASE WHEN domain='aviation' THEN year END),
        GROUP_CONCAT(DISTINCT CASE WHEN domain='construction' THEN official END)
        FROM records GROUP BY group_id""").fetchall():
        periods = {faa_period(int(y)) for y in years.split(",")} if years else set()
        temporal = next(iter(periods)) if len(periods) == 1 else "quarantine"
        original = set(officials.split(",")) if officials else set()
        official_safe = next(iter(original)) if len(original) == 1 else "quarantine"
        connection.execute(
            """UPDATE records SET grouped=?, temporal=?, official_safe=?
            WHERE group_id=?""",
            (grouped_split(group_id, seed), temporal, official_safe, group_id),
        )
    # Partial-year aviation rows are ineligible for all train/validation/test experiments.
    connection.execute("UPDATE records SET grouped='demo' WHERE year=2026")
    connection.execute("UPDATE records SET temporal='not_applicable' WHERE domain!='aviation'")
    connection.execute(
        "UPDATE records SET official_safe='not_applicable' WHERE domain!='construction'"
    )
    connection.execute("""UPDATE records SET grouped='excluded',temporal='excluded',
        official_safe='excluded' WHERE excluded!='' """)
    connection.commit()
    return duplicate_counts


def select_training_sample(connection, budget):
    # One representative per group/source/label/year. Conflicting source labels in a
    # connected group are excluded from the supervised sample, not silently reconciled.
    connection.execute("""CREATE TABLE label_conflicts AS SELECT group_id,domain
        FROM records WHERE label!='' GROUP BY group_id,domain
        HAVING COUNT(DISTINCT label)>1""")
    connection.execute("CREATE UNIQUE INDEX conflict_lookup ON label_conflicts(group_id,domain)")
    connection.execute("""CREATE TABLE candidates AS
        SELECT * FROM (SELECT r.*, ROW_NUMBER() OVER (
            PARTITION BY group_id,domain ORDER BY sample_rank) AS rank_in_group
            FROM records r WHERE excluded='' AND label!='' AND (
                (domain='aviation' AND temporal='train') OR
                (domain='construction' AND official_safe='train') OR
                (domain='pipeline' AND grouped='train'))
            AND NOT EXISTS (SELECT 1 FROM label_conflicts b WHERE b.group_id=r.group_id
                AND b.domain=r.domain))
        WHERE rank_in_group=1""")
    connection.execute("CREATE INDEX candidate_strata ON candidates(domain,label,year,sample_rank)")
    strata = connection.execute("""SELECT label,year,COUNT(*) FROM candidates
        WHERE domain='aviation' GROUP BY label,year ORDER BY label,year""").fetchall()
    total = sum(n for _, _, n in strata)
    remaining = min(budget, total)
    # Largest-remainder proportional allocation is deterministic, with reported coverage.
    quotas = [
        (label, year, remaining * n // total, (remaining * n) % total) for label, year, n in strata
    ]
    leftover = remaining - sum(q for _, _, q, _ in quotas)
    extra = {
        (label, year)
        for label, year, _, _ in sorted(quotas, key=lambda r: (-r[3], r[0], r[1]))[:leftover]
    }
    for label, year, quota, _ in quotas:
        connection.execute(
            """UPDATE records SET selected=1 WHERE idx IN (
            SELECT idx FROM candidates WHERE domain='aviation' AND label=? AND year=?
            ORDER BY sample_rank LIMIT ?)""",
            (label, year, quota + int((label, year) in extra)),
        )
    connection.execute(
        "UPDATE records SET selected=1 WHERE idx IN (SELECT idx FROM candidates "
        "WHERE domain!='aviation')"
    )
    connection.commit()


def export_frozen(connection, output):
    schema = pa.schema(
        [
            ("record_id", pa.string()),
            ("group_id", pa.string()),
            ("domain", pa.string()),
            ("grouped_split", pa.string()),
            ("faa_temporal_split", pa.string()),
            ("fire_door_official_split", pa.string()),
            ("fire_door_safe_split", pa.string()),
            ("selected_for_training", pa.bool_()),
            ("exclusion_reason", pa.string()),
            ("holdout_construction", pa.string()),
            ("holdout_aviation", pa.string()),
            ("holdout_pipeline", pa.string()),
        ]
    )
    metadata = connection.execute("""SELECT r.record_id,r.group_id,r.domain,r.grouped,r.temporal,
        r.official,r.official_safe,r.selected,r.excluded,g.domains FROM records r
        JOIN groups g ON r.group_id=g.group_id ORDER BY r.idx""")
    with pq.ParquetWriter(output / "assignments.parquet", schema) as writer:
        batch = []
        for row in metadata:
            holdouts = [
                row[3]
                if row[3] in {"demo", "excluded"}
                else "test"
                if domain in row[9].split(",")
                else "train"
                if row[3] == "train"
                else "validation"
                for domain in ("construction", "aviation", "pipeline")
            ]
            batch.append(
                dict(zip(schema.names, [*row[:7], bool(row[7]), row[8], *holdouts], strict=True))
            )
            if len(batch) == 5000:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
    selected = {
        row[0] for row in connection.execute("SELECT record_id FROM records WHERE selected=1")
    }
    record_schema = pa.schema(
        [
            ("record_id", pa.string()),
            ("domain", pa.string()),
            ("clean_text", pa.string()),
            ("record_json", pa.string()),
        ]
    )
    with (
        (output / "training_sample.jsonl").open("w") as sample,
        pq.ParquetWriter(output / "cleaned.parquet", record_schema) as writer,
    ):
        batch = []
        for line in (output / "cleaned.jsonl").open():
            record = Record.model_validate_json(line)
            if record.record_id in selected:
                record.split = "train"
                record.document_metadata["experiment"] = {
                    "aviation": "faa_temporal",
                    "construction": "fire_door_official_safe",
                    "pipeline": "grouped",
                }[record.domain]
                sample.write(record.model_dump_json() + "\n")
            batch.append(
                {
                    "record_id": record.record_id,
                    "domain": record.domain,
                    "clean_text": record.clean_text,
                    "record_json": line.strip(),
                }
            )
            if len(batch) == 5000:
                writer.write_table(pa.Table.from_pylist(batch, schema=record_schema))
                batch = []
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=record_schema))


def audit(connection, duplicates):
    def distribution(column):
        return [
            dict(zip(("domain", column, "rows"), row, strict=True))
            for row in connection.execute(
                f"SELECT domain,{column},COUNT(*) FROM records "
                f"GROUP BY domain,{column} ORDER BY domain,{column}"
            )
        ]

    length_stats = []
    for domain, total, mean, minimum, maximum in connection.execute("""SELECT domain,COUNT(*),
            AVG(words),MIN(words),MAX(words) FROM records GROUP BY domain"""):
        median = connection.execute(
            "SELECT words FROM records WHERE domain=? ORDER BY words LIMIT 1 OFFSET ?",
            (domain, total // 2),
        ).fetchone()[0]
        length_stats.append(
            {
                "domain": domain,
                "rows": total,
                "mean_words": mean,
                "median_words": median,
                "min_words": minimum,
                "max_words": maximum,
            }
        )
    return {
        "duplicate_extra_rows_by_key": duplicates,
        "group_sizes": {
            str(size): count
            for size, count in connection.execute(
                "SELECT members,COUNT(*) FROM groups GROUP BY members"
            )
        },
        "text_lengths": length_stats,
        **{
            column: distribution(column)
            for column in (
                "label",
                "year",
                "pii",
                "excluded",
                "grouped",
                "temporal",
                "official_safe",
                "selected",
            )
        },
        "limitations": [
            "Pattern redaction requires human review; not anonymization certification",
            "Template fingerprints cover numeric-slot/punctuation variants, not all near duplicates",
            "No manually verified gold labels; frozen assignments are not gold annotations",
            "Per-source samples are separate experiments, not a pooled multi-domain training set",
            "PHMSA preferred final/latest selection and vendor holdouts remain pending",
        ],
    }


def validate(connection):
    # Group isolation, except deliberately excluded/demo records, must hold globally.
    for column in ("grouped", "temporal", "official_safe"):
        bad = connection.execute(f"""SELECT COUNT(*) FROM (SELECT group_id FROM records
            WHERE {column} IN ('train','validation','test') GROUP BY group_id
            HAVING COUNT(DISTINCT {column})>1)""").fetchone()[0]
        if bad:
            raise ValueError(f"{column}: {bad} groups cross evaluation splits")
    if connection.execute("SELECT COUNT(*) FROM records WHERE year=2026 AND selected=1").fetchone()[
        0
    ]:
        raise ValueError("Partial-year FAA rows entered training")


def finalize(connection, output, sources, size, duplicates, budget):
    print("Exporting frozen assignments and Parquet", flush=True)
    if (output / "manifest.json").exists():
        raise ValueError("Cannot rewrite a frozen snapshot")
    validate(connection)
    export_frozen(connection, output)
    report = audit(connection, duplicates)
    (output / "quality_report.json").write_text(json.dumps(report, indent=2) + "\n")
    artifacts = {
        p.name: checksum(p) for p in output.iterdir() if p.suffix in {".jsonl", ".parquet", ".json"}
    }
    manifest = {
        "policy_version": POLICY_VERSION,
        "status": "frozen",
        "rows": size,
        "seed": "inspectra-corpus-v1",
        "sources": sources,
        "artifacts": artifacts,
        "faa_temporal": {
            "train": "through 2023",
            "validation": 2024,
            "test": 2025,
            "demo_only": 2026,
            "cross_period_groups": "quarantine",
        },
        "faa_training_budget": budget,
        "grouped_proportions": [0.70, 0.15, 0.15],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"rows": size, "status": "frozen", "output": str(output)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/corpus-v1"))
    parser.add_argument("--faa-train-size", type=int, default=75000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Output already exists; frozen snapshots cannot be overwritten. Use a new path."
        )
    if args.output.resolve().is_relative_to(args.raw.resolve()):
        parser.error("Output must be outside raw storage")
    if args.faa_train_size < 1:
        parser.error("Training sample size must be positive")
    args.output.mkdir(parents=True)
    connection = sqlite3.connect(args.output / "index.sqlite")
    try:
        sources, size = index_corpus(args.raw, args.output, connection)
        print(f"Grouping {size} records", flush=True)
        duplicates = group_and_split(connection, size, "inspectra-corpus-v1")
        select_training_sample(connection, args.faa_train_size)
        validate(connection)
        finalize(connection, args.output, sources, size, duplicates, args.faa_train_size)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
