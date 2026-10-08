import json

import pytest

from inspection_nlp.documents import parse_document
from inspection_nlp.evaluation import (
    GoldExample,
    audit_partition,
    benchmark_parsers,
    load_gold,
    metrics,
    partition,
    perturbation_checks,
    score_predictions,
)
from inspection_nlp.findings import with_findings
from inspection_nlp.schemas import Entity, Record


def example(text, vendor="Unseen Vendor", date="2026-01-01"):
    r = parse_document(
        text.encode(), text + ".txt", report_metadata={"vendor": vendor, "report_date": date}
    )[0]
    start = r.display_text.lower().find("crack")
    payload = r.model_dump()
    payload["entities"] = [
        Entity(
            label="DEFECT",
            text=r.display_text[start : start + 7],
            evidence_start=start,
            evidence_end=start + 7,
            assertion="present",
            confidence=1,
            extraction_method="human",
        ).model_dump()
    ]
    gold = with_findings(Record.model_validate(payload))
    return GoldExample(r, gold, r.report_id, ["annotator-a", "annotator-b"])


def test_fixed_labels_count_unseen_reference_and_assertions():
    gold = example("Spindle cracked.")
    empty = gold.original
    score = score_predictions([gold], [empty])
    assert score["entities"]["recall"] == 0
    assert score["per_label"]["DEFECT"]["reference"] == 1
    assert score["joint_defect_assertion"]["reference"] == 1
    assert metrics({1}, {1, 2})["recall"] == 0.5


def test_vendor_and_template_isolation():
    a = example("Spindle cracked at 3 mm.", "A")
    b = example("Spindle cracked at 4 mm.", "B")
    assignments = partition([a, b], mode="vendor", holdout=["B"])
    assert set(assignments.values()) == {"test"}  # Template bridge quarantines training leakage.
    audit_partition([a, b], assignments, "vendor")
    with pytest.raises(ValueError, match="cross partitions"):
        audit_partition(
            [a, b], {a.original.record_id: "train", b.original.record_id: "test"}, "vendor"
        )
    with pytest.raises(ValueError, match="do not match"):
        partition([a], mode="vendor", holdout=["missing"])


def test_temporal_bridge_quarantines():
    a = example("Spindle cracked at 3 mm.", "A", "2025-01-01")
    b = example("Spindle cracked at 4 mm.", "B", "2026-01-01")
    assignments = partition(
        [a, b], mode="temporal", train_end="2025-06-01", validation_end="2025-12-31"
    )
    assert set(assignments.values()) == {"quarantine"}


def test_gold_gate_and_valid_import(tmp_path):
    e = example("Spindle cracked.")
    row = {
        "record": e.original.model_dump(),
        "entities": [x.model_dump() for x in e.reference.entities],
        "findings": [f.model_dump() for f in e.reference.findings],
        "privacy_reviewed": True,
        "annotation_status": "adjudicated",
        "annotation_source": "human",
        "annotator_ids": ["a", "b"],
        "adjudicator_id": "c",
        "annotation_version": "v1",
    }
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(row) + "\n")
    assert len(load_gold(path)) == 1
    path.write_text(json.dumps({**row, "annotator_ids": ["a"]}) + "\n")
    with pytest.raises(ValueError, match="Two independent"):
        load_gold(path)


def test_perturbations_and_parser_failures(tmp_path):
    r = example("Ceramic spindle cracked.").original
    checks = perturbation_checks(r)
    assert checks["metadata_vendor_substitution"] and checks["horizontal_whitespace"]
    path = tmp_path / "empty.txt"
    path.write_text("")
    results = benchmark_parsers([{"path": str(path), "privacy_reviewed": True}])
    assert results[0]["error"] and results[0]["records"] == 0
    with pytest.raises(ValueError, match="privacy-reviewed"):
        benchmark_parsers([{"path": str(path)}])


def test_training_selects_validation_and_sealed_evaluation(tmp_path):
    import hashlib
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    script = Path(__file__).resolve().parents[1] / "scripts/generalisation.py"
    spec = importlib.util.spec_from_file_location("generalisation_cli", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    examples = [
        example(text) for text in ["Spindle cracked.", "Roller cracked.", "Conductor cracked."]
    ]
    rows = [
        {
            "record": e.original.model_dump(),
            "entities": [x.model_dump() for x in e.reference.entities],
            "findings": [f.model_dump() for f in e.reference.findings],
            "privacy_reviewed": True,
            "annotation_status": "adjudicated",
            "annotation_source": "human",
            "annotator_ids": ["a", "b"],
            "adjudicator_id": "c",
            "annotation_version": "synthetic-test-only",
        }
        for e in examples
    ]
    path = tmp_path / "synthetic_test_annotations.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "label_set": list(module.LABELS),
                "mode": "grouped",
                "holdout": [],
                "assignments": {
                    e.original.record_id: split
                    for e, split in zip(examples, ["train", "validation", "test"], strict=True)
                },
            }
        )
    )
    model, report = tmp_path / "model", tmp_path / "training.json"
    module.train(SimpleNamespace(input=path, manifest=manifest, model=model, report=report))
    assert json.loads(report.read_text())["selected_epochs"] in {10, 20}
    output = tmp_path / "evaluation.json"
    module.evaluate(SimpleNamespace(input=path, manifest=manifest, model=model, output=output))
    measured = json.loads(output.read_text())
    assert measured["model_isolation"] == "verified_manifest"
    assert set(measured["experiments"]) == {"rules", "contextual", "ner", "hybrid"}
    assert measured["experiments"]["ner"]["records"] == 1
