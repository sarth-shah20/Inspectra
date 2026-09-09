import json

import pytest

from inspection_nlp.analytics import entity_counts, review_summary
from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract
from inspection_nlp.reviews import append_review, human_entities, review_payload


def record():
    return extract(
        parse_document(b"Valve crack measured at 3 mm.", "note.txt", domain="pipeline")[0]
    )


def test_review_payload_replaces_rule_provenance(tmp_path):
    item = record()
    rows = [entity.model_dump() for entity in item.entities]
    payload = review_payload(item, rows, "Confirmed by reviewer")
    assert payload["label_origin"] == "human"
    assert {entity["extraction_method"] for entity in payload["corrected_entities"]} == {"human"}
    append_review(tmp_path / "reviews.jsonl", payload)
    assert json.loads((tmp_path / "reviews.jsonl").read_text())["note"] == "Confirmed by reviewer"


def test_review_rejects_overlapping_spans():
    item = record()
    with pytest.raises(ValueError, match="overlap"):
        human_entities(
            item,
            [
                {
                    "label": "COMPONENT",
                    "assertion": "present",
                    "evidence_start": 0,
                    "evidence_end": 5,
                },
                {"label": "DEFECT", "assertion": "present", "evidence_start": 3, "evidence_end": 8},
            ],
        )


def test_analytics_summary():
    item = record()
    assert entity_counts([item]) == [
        {"entity": "COMPONENT", "count": 1},
        {"entity": "DEFECT", "count": 1},
        {"entity": "MEASUREMENT", "count": 1},
    ]
    assert review_summary([item])["entities"] == 3
