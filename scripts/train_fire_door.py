"""Train the fixed fire-door TF-IDF baseline without using test records for selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import sklearn

from inspection_nlp.classification import (
    build_pipeline,
    class_counts,
    evaluate,
    load_fire_door_splits,
)
from inspection_nlp.ingestion import checksum


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/processed/corpus-v1"))
    parser.add_argument("--model-dir", type=Path, default=Path("models/fire-door-tfidf-v1"))
    parser.add_argument("--report", type=Path, default=Path("reports/fire_door_baseline.json"))
    args = parser.parse_args()
    manifest_path = args.snapshot / "manifest.json"
    if not manifest_path.exists():
        parser.error("The corpus snapshot must be frozen and include manifest.json")
    if args.model_dir.exists() or args.report.exists():
        parser.error("Model directory and report must not already exist; model runs are immutable")

    splits = load_fire_door_splits(args.snapshot)
    if not all(splits.values()):
        parser.error("Duplicate-safe fire-door splits must each contain eligible labelled records")
    candidates = [
        {"C": c, "class_weight": class_weight}
        for c in (0.3, 1.0, 3.0)
        for class_weight in (None, "balanced")
    ]
    validation_runs = []
    for candidate in candidates:
        model = build_pipeline(c=candidate["C"], class_weight=candidate["class_weight"])
        model.fit([item.text for item in splits["train"]], [item.label for item in splits["train"]])
        validation_runs.append({**candidate, **evaluate(model, splits["validation"])})
    best = max(
        validation_runs,
        key=lambda run: (
            run["macro_f1"],
            run["weighted_f1"],
            -run["C"],
            run["class_weight"] is None,
        ),
    )
    model = build_pipeline(c=best["C"], class_weight=best["class_weight"])
    model.fit([item.text for item in splits["train"]], [item.label for item in splits["train"]])
    test = evaluate(model, splits["test"])

    args.model_dir.mkdir(parents=True)
    joblib.dump(model, args.model_dir / "model.joblib")
    metadata = {
        "model": "word+character TF-IDF + LogisticRegression",
        "sklearn_version": sklearn.__version__,
        "selection_metric": "validation macro F1",
        "selected_parameters": {"C": best["C"], "class_weight": best["class_weight"]},
        "snapshot_manifest_sha256": checksum(manifest_path),
        "eligible_records_by_split": {split: len(items) for split, items in splits.items()},
        "class_counts_by_split": {split: class_counts(items) for split, items in splits.items()},
        "test_set_usage": "evaluated once after validation-based selection; never used to choose parameters",
        "limitations": [
            "Source-provided document labels are not token-level entity annotations.",
            "Metrics apply only to the duplicate-safe supplied fire-door split.",
            "No claim of transfer to aviation, pipeline, vendors, or unseen terminology.",
        ],
    }
    (args.model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    report = {
        "experiment": "fire-door-tfidf-v1",
        "metadata": metadata,
        "validation_candidates": [
            {key: value for key, value in run.items() if key != "predictions"}
            for run in validation_runs
        ],
        "test": {key: value for key, value in test.items() if key != "predictions"},
        "test_predictions": test["predictions"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({"selected": metadata["selected_parameters"], "test": report["test"]}, indent=2)
    )


if __name__ == "__main__":
    main()
