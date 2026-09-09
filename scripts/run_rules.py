"""Run generic/domain rule ablation on a local pilot; counts are not accuracy metrics."""

import argparse
import json
from collections import Counter
from pathlib import Path

from inspection_nlp.extraction import extract
from inspection_nlp.schemas import Record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/pilot/records.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/rules/records.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("reports/rules_smoke.json"))
    args = parser.parse_args()
    raw = Path("data/raw").resolve()
    for output in (args.output, args.report):
        if output.resolve() == args.input.resolve() or output.resolve().is_relative_to(raw):
            parser.error("Outputs must not overwrite the input or raw storage")
    if args.output.resolve() == args.report.resolve():
        parser.error("Output records and report must be different paths")
    counts = Counter()
    generic_counts = Counter()
    domain_counts = Counter()
    statuses = Counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.input.open() as source, args.output.open("w") as target:
        for line in source:
            record = Record.model_validate_json(line)
            generic = extract(record, use_domain=False)
            adapted = extract(record)
            counts[record.domain] += 1
            generic_counts.update(f"{record.domain}:{e.label}" for e in generic.entities)
            domain_counts.update(f"{record.domain}:{e.label}" for e in adapted.entities)
            statuses[adapted.mapping_status] += 1
            target.write(adapted.model_dump_json() + "\n")
    report = {
        "purpose": "integration smoke test; match counts are not precision, recall, or F1",
        "dictionary_origin": "hand-authored starter terms; no tuning on pilot test text",
        "records_by_domain": dict(counts),
        "generic_entity_counts": dict(generic_counts),
        "adapted_entity_counts": dict(domain_counts),
        "mapping_status_counts": dict(statuses),
        "limitations": [
            "uncalibrated confidence",
            "heuristic assertion scope",
            "no gold annotations",
            "no demonstrated generalization accuracy",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"records": sum(counts.values()), "report": str(args.report)}))


if __name__ == "__main__":
    main()
