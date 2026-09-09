"""Reproducible source-specific document classification baselines."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline


@dataclass(frozen=True)
class ClassificationExample:
    """A source-labelled document, with no structured target included in its text."""

    record_id: str
    text: str
    label: str


def load_fire_door_splits(snapshot: Path) -> dict[str, list[ClassificationExample]]:
    """Load the duplicate-safe supplied split variant from a frozen corpus snapshot."""
    assignments = {}
    import pyarrow.parquet as pq

    for batch in pq.ParquetFile(snapshot / "assignments.parquet").iter_batches(batch_size=5000):
        for row in batch.to_pylist():
            if row["domain"] == "construction":
                assignments[row["record_id"]] = row

    splits: dict[str, list[ClassificationExample]] = {"train": [], "validation": [], "test": []}
    with (snapshot / "cleaned.jsonl").open() as source:
        for line in source:
            record = json.loads(line)
            if record["domain"] != "construction":
                continue
            assignment = assignments[record["record_id"]]
            split = assignment["fire_door_safe_split"]
            label = record["structured_source_fields"].get("Classification_English", "").strip()
            if split not in splits or not label or not record["clean_text"]:
                continue
            splits[split].append(
                ClassificationExample(record["record_id"], record["clean_text"], label)
            )
    return splits


def load_source_splits(
    snapshot: Path,
    *,
    domain: str,
    split_column: str,
    labels: list[str],
) -> dict[str, list[ClassificationExample]]:
    """Load one representative per consistent group for a source classification task."""
    if split_column not in {"temporal", "grouped"}:
        raise ValueError("Only frozen temporal or grouped source assignments are supported")
    placeholders = ",".join("?" for _ in labels)
    connection = sqlite3.connect(f"file:{(snapshot / 'index.sqlite').resolve()}?mode=ro", uri=True)
    try:
        selected = connection.execute(
            f"""SELECT record_id, label FROM records
            WHERE domain=? AND selected=1 AND label IN ({placeholders})""",
            [domain, *labels],
        ).fetchall()
        evaluation = connection.execute(
            f"""WITH conflicts AS (
                SELECT group_id FROM records WHERE domain=? AND label!=''
                GROUP BY group_id HAVING COUNT(DISTINCT label)>1
            ), representatives AS (
                SELECT r.group_id, MIN(r.record_id) AS record_id, MIN(r.label) AS label,
                    MIN(r.{split_column}) AS split
                FROM records r LEFT JOIN conflicts c USING(group_id)
                WHERE r.domain=? AND r.{split_column} IN ('validation','test')
                  AND r.excluded='' AND r.label IN ({placeholders}) AND c.group_id IS NULL
                GROUP BY r.group_id
            ) SELECT record_id, label, split FROM representatives""",
            [domain, domain, *labels],
        ).fetchall()
    finally:
        connection.close()
    ids = {"train": dict(selected), "validation": {}, "test": {}}
    for record_id, label, split in evaluation:
        ids[split][record_id] = label
    examples = {split: [] for split in ids}
    remaining = {split: dict(records) for split, records in ids.items()}
    with (snapshot / "cleaned.jsonl").open() as source:
        for line in source:
            record = json.loads(line)
            for split, lookup in remaining.items():
                label = lookup.pop(record["record_id"], None)
                if label is not None:
                    examples[split].append(
                        ClassificationExample(record["record_id"], record["clean_text"], label)
                    )
    if any(remaining.values()):
        raise ValueError("Frozen index references missing canonical record")
    return examples


def class_counts(examples: list[ClassificationExample]) -> dict[str, int]:
    return dict(sorted(Counter(example.label for example in examples).items()))


def build_pipeline(
    *, c: float, class_weight: str | None, include_character: bool = True
) -> Pipeline:
    """Build a word baseline, optionally adding character features for compact text corpora."""
    feature_steps = [("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1))]
    if include_character:
        feature_steps.append(
            (
                "character",
                TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True),
            )
        )
    features = FeatureUnion(feature_steps)
    classifier = LogisticRegression(
        C=c,
        class_weight=class_weight,
        max_iter=2000,
        random_state=20260909,
        solver="lbfgs",
    )
    return Pipeline([("features", features), ("classifier", classifier)])


def evaluate(model: Pipeline, examples: list[ClassificationExample]) -> dict:
    predicted = model.predict([example.text for example in examples]).tolist()
    return evaluate_predictions(examples, predicted)


def evaluate_predictions(examples: list[ClassificationExample], predicted: list[str]) -> dict:
    """Evaluate predictions already generated from a train-fitted feature representation."""
    labels = sorted({example.label for example in examples})
    actual = [example.label for example in examples]
    return {
        "records": len(examples),
        "macro_f1": f1_score(actual, predicted, average="macro", zero_division=0),
        "weighted_f1": f1_score(actual, predicted, average="weighted", zero_division=0),
        "per_class": classification_report(
            actual, predicted, labels=labels, output_dict=True, zero_division=0
        ),
        "predictions": [
            {"record_id": example.record_id, "actual": true, "predicted": pred}
            for example, true, pred in zip(examples, actual, predicted, strict=True)
        ],
    }


def predict(model: Pipeline, text: str) -> dict[str, float | str]:
    """Return the source-taxonomy class and its raw model score for one narrative."""
    probabilities = model.predict_proba([text])[0]
    index = probabilities.argmax()
    return {"label": model.classes_[index], "score": float(probabilities[index])}
