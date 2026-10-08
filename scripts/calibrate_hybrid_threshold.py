"""Evaluate provisional inclusion thresholds on validation silver labels only."""

import argparse
import json
from pathlib import Path

from inspection_nlp.hybrid import extract_hybrid
from inspection_nlp.schemas import Record


def calibrate(rows, model):
    results = []
    for threshold in (0.5, 0.75, 0.95):
        predicted, gold = set(), set()
        for i, row in enumerate(rows):
            r = Record(
                record_id=row["record_id"],
                source_dataset="silver",
                source_record_id=row["record_id"],
                source_event_id=row["group_id"],
                source_document="silver",
                source_sha256="silver",
                source_row=2,
                domain=row["domain"],
                schema_version="silver",
                source_column_mapping={},
                clean_text=row["clean_text"],
                display_text=row["clean_text"],
                label_origin="weak",
            )
            result = extract_hybrid(r, model, threshold=threshold)
            predicted |= {(i, e.evidence_start, e.evidence_end, e.label) for e in result.entities}
            gold |= {
                (i, e["evidence_start"], e["evidence_end"], e["label"]) for e in row["entities"]
            }
        correct = len(predicted & gold)
        precision = correct / len(predicted) if predicted else 0
        recall = correct / len(gold) if gold else 0
        results.append(
            {
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/annotations/ai_annotated.jsonl"))
    parser.add_argument("--model", type=Path, default=Path("models/silver-ner-v1"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/provisional_hybrid_calibration_v2.json")
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite report")
    with args.input.open() as stream:
        rows = [row for line in stream if (row := json.loads(line))["split"] == "validation"]
    results = calibrate(rows, args.model)
    best = max(results, key=lambda x: (x["f1"], x["threshold"]))
    report = {
        "scope": "AI-assisted validation labels; not human-validated accuracy or probability calibration.",
        "policy_version": "all-candidates-threshold-v2",
        "records": len(rows),
        "supersedes": "provisional_hybrid_calibration.json",
        "selected_threshold": best["threshold"],
        "validation_candidates": results,
        "dashboard_provisional_threshold": 0.5,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(best))


if __name__ == "__main__":
    main()
