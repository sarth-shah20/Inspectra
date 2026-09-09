"""Train a sealed FAA or PHMSA source-specific text-classification baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import sklearn
import yaml
from sklearn.base import clone

from inspection_nlp.classification import (
    build_pipeline,
    class_counts,
    evaluate,
    evaluate_predictions,
    load_source_splits,
)
from inspection_nlp.ingestion import checksum

TASKS = {
    "faa": {"config": "faa_part_condition", "domain": "aviation", "name": "faa-part-condition"},
    "phmsa": {"config": "phmsa_cause", "domain": "pipeline", "name": "phmsa-cause"},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=TASKS)
    parser.add_argument("--snapshot", type=Path, default=Path("data/processed/corpus-v1"))
    parser.add_argument("--config", type=Path, default=Path("configs/classification.yaml"))
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    task = TASKS[args.task]
    model_dir = args.model_dir or Path(f"models/{task['name']}-tfidf-v1")
    report_path = args.report or Path(f"reports/{task['name']}_baseline.json")
    if model_dir.exists() or report_path.exists():
        parser.error("Model directory and report must not already exist; model runs are immutable")
    config = yaml.safe_load(args.config.read_text())[task["config"]]
    splits = load_source_splits(
        args.snapshot,
        domain=task["domain"],
        split_column=config["split_column"],
        labels=config["labels"],
    )
    if not all(splits.values()):
        parser.error("Each frozen split needs eligible examples for every experiment")
    # Fixed before seeing validation or test performance. A broad search is deferred
    # until source baselines and gold entity work are stable.
    candidate = {"C": 1.0, "class_weight": "balanced"}
    train_text = [item.text for item in splits["train"]]
    train_labels = [item.label for item in splits["train"]]
    validation_text = [item.text for item in splits["validation"]]
    feature_template = build_pipeline(
        c=1.0, class_weight=None, include_character=False
    ).named_steps["features"]
    features = clone(feature_template)
    train_matrix = features.fit_transform(train_text)
    validation_matrix = features.transform(validation_text)
    classifier = build_pipeline(
        c=candidate["C"], class_weight=candidate["class_weight"], include_character=False
    ).named_steps["classifier"]
    classifier.fit(train_matrix, train_labels)
    validation = {
        **candidate,
        **evaluate_predictions(
            splits["validation"], classifier.predict(validation_matrix).tolist()
        ),
    }
    model = build_pipeline(
        c=candidate["C"], class_weight=candidate["class_weight"], include_character=False
    )
    model.steps[0] = ("features", features)
    model.steps[1] = ("classifier", classifier)
    test = evaluate(model, splits["test"])
    model_dir.mkdir(parents=True)
    joblib.dump(model, model_dir / "model.joblib")
    metadata = {
        "task": task["name"],
        "domain": task["domain"],
        "input": "canonical clean_text only; source target field excluded",
        "features": "word TF-IDF (1,2-grams)",
        "labels": config["labels"],
        "label_selection": config["selection_rule"],
        "split_policy": config["split_column"],
        "sklearn_version": sklearn.__version__,
        "fixed_parameters": candidate,
        "selection_metric": "none; fixed initial baseline",
        "snapshot_manifest_sha256": checksum(args.snapshot / "manifest.json"),
        "eligible_records_by_split": {name: len(items) for name, items in splits.items()},
        "class_counts_by_split": {name: class_counts(items) for name, items in splits.items()},
        "test_set_usage": "evaluated once after fixed-configuration training",
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    output = {
        "experiment": f"{task['name']}-tfidf-v1",
        "metadata": metadata,
        "validation": {key: value for key, value in validation.items() if key != "predictions"},
        "test": {key: value for key, value in test.items() if key != "predictions"},
        "test_predictions": test["predictions"],
    }
    report_path.write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                "task": task["name"],
                "parameters": candidate,
                "test_macro_f1": test["macro_f1"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
