"""Count all local source rows without copying narratives into reports."""

import json
from pathlib import Path

from inspection_nlp.ingestion import checksum, rows


def main():
    raw = Path("data/raw")
    results = []
    for path in sorted(raw.rglob("*")):
        if path.suffix not in {".xlsx", ".csv", ".txt"}:
            continue
        count = empty = 0
        ids = set()
        duplicates = 0
        columns = []
        for _, row in rows(path):
            count += 1
            columns = list(row)
            narrative = row.get("English", row.get("Discrepancy", row.get("NARRATIVE", "")))
            empty += not narrative.strip()
            event = row.get("OperatorControlNumber", row.get("REPORT_NUMBER", row.get("RPTID")))
            if event:
                duplicates += event in ids
                ids.add(event)
        results.append(
            {
                "file": str(path.relative_to(raw)),
                "sha256": checksum(path),
                "rows": count,
                "empty_narratives": empty,
                "columns": columns,
                "repeated_event_rows_within_file": duplicates,
            }
        )
    output = Path("reports/source_audit.json")
    output.write_text(json.dumps({"files": results}, indent=2) + "\n")
    print(json.dumps({r["file"]: r["rows"] for r in results}, indent=2))


if __name__ == "__main__":
    main()
