from pathlib import Path

import pytest

from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract

SAMPLES = Path("samples/demo")


@pytest.mark.parametrize(
    ("filename", "domain", "expected"),
    [
        (
            "synthetic_fire_door_inspection.docx",
            "construction",
            {("COMPONENT", "fire door"), ("DEFECT", "frame gap"), ("DEFECT", "missing")},
        ),
        (
            "synthetic_aviation_maintenance_inspection.docx",
            "aviation",
            {("DEFECT", "loose"), ("DEFECT", "crack"), ("COMPONENT", "actuator")},
        ),
        (
            "synthetic_industrial_pump_inspection.docx",
            "general",
            {("MEASUREMENT", "8.6 mm"), ("DEFECT", "missing"), ("DEFECT", "loose")},
        ),
        (
            "synthetic_pipeline_integrity_inspection.docx",
            "pipeline",
            {("COMPONENT", "valve"), ("DEFECT", "corrosion"), ("DEFECT", "cracked")},
        ),
    ],
)
def test_synthetic_docx_demo_extracts_expected_explicit_evidence(filename, domain, expected):
    record = parse_document((SAMPLES / filename).read_bytes(), filename, domain=domain)[0]
    result = extract(record)
    observed = {(entity.label, entity.text.casefold()) for entity in result.entities}
    assert not result.contains_sensitive_fields
    assert result.mapping_status == "review_required"
    assert expected <= observed
    for entity in result.entities:
        assert result.display_text[entity.evidence_start : entity.evidence_end] == entity.text
