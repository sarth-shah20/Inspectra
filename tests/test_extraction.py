import json

import pytest

from inspection_nlp.documents import parse_document
from inspection_nlp.export import export_csv, export_json, highlight
from inspection_nlp.extraction import extract


def run(text, domain="general", contextual=True):
    return extract(parse_document(text.encode(), "test.txt", domain=domain)[0], contextual=contextual)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("No crack observed.", "negated"),
        ("Possible leak at the valve.", "possible"),
        ("The crack was repaired.", "resolved"),
        ("Previous crack documented.", "historical"),
        ("The valve cracked.", "present"),
        ("Crack was not found.", "negated"),
        ("Leak suspected.", "possible"),
    ],
)
def test_assertion(text, expected):
    defects = [e for e in run(text).entities if e.label == "DEFECT"]
    assert defects and all(e.assertion == expected for e in defects)


def test_clause_boundary():
    defects = [
        e for e in run("No crack observed, but valve leaking.").entities if e.label == "DEFECT"
    ]
    assert [e.assertion for e in defects] == ["negated", "present"]


def test_domain_ablation():
    for domain, component in [
        ("construction", "door closer"),
        ("aviation", "landing gear"),
        ("pipeline", "valve"),
    ]:
        text = f"The {component} is damaged."
        assert not any(e.label == "COMPONENT" for e in run(text, contextual=False).entities)
        assert any(e.label == "COMPONENT" for e in run(text, domain).entities)
        assert any(e.label == "DEFECT" for e in run(text).entities)


def test_unfamiliar_term_abstention():
    result = run("The zorbulator exhibits flensing.")
    assert not result.entities
    assert result.mapping_status == "review_required"
    assert result.review_candidates
    assert run("The zorbulator is cracked.").mapping_status == "review_required"


def test_offsets_after_privacy_redaction():
    result = run("a@example.com reports a 3 mm crack on 2024-01-02.")
    assert {"MEASUREMENT", "DEFECT", "DATE"} <= {e.label for e in result.entities}
    for entity in result.entities:
        assert result.display_text[entity.evidence_start : entity.evidence_end] == entity.text
    assert result.reported_severity is None


def test_reported_severity_only():
    assert run("Critical crack found.").reported_severity == "Critical"
    assert run("No severe crack found.").reported_severity is None


def test_exports_and_safe_highlighting():
    result = run("<script>alert(1)</script> crack found.")
    rendered = highlight(result)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered and "<mark" in rendered
    assert json.loads(export_json([result]))[0]["entities"][0]["text"] == "crack"
    assert "DEFECT,crack,present" in export_csv([result])
