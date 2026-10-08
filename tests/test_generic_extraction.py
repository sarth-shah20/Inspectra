from inspection_nlp import extraction
from inspection_nlp.documents import parse_document


def test_generic_unknown_component():
    r = parse_document(b"Ceramic spindle cracked.", "textile.txt", domain="textile")[0]
    result = extraction.extract(r)
    assert any(e.label == "DEFECT" for e in result.entities)
    if extraction.english_model() is not None:
        assert any(e.text == "spindle" and e.label == "COMPONENT" for e in result.entities)
    assert result.domain == "textile"


def test_degraded_and_unknown_evidence(monkeypatch):
    monkeypatch.setattr(extraction, "english_model", lambda: None)
    r = parse_document(b"The zorbulator exhibits flensing.", "new.txt")[0]
    result = extraction.extract(r)
    assert result.review_candidates[0].text == r.display_text[:-1]
    assert not result.entities
    assert "rules_only_coverage" in result.quality_flags
    assert result.document_metadata["extraction_mode"] == "rules_only"


def test_custom_pack(tmp_path):
    pack = tmp_path / "custom.yaml"
    pack.write_text("version: textile-v1\nentities:\n  DEFECT: [flensing]\n")
    r = parse_document(b"The zorbulator exhibits flensing.", "new.txt")[0]
    result = extraction.extract(r, pack_paths=(str(pack),))
    assert any(e.text == "flensing" for e in result.entities)


def test_pack_changes_invalidate_cache(tmp_path):
    pack = tmp_path / "custom.yaml"
    pack.write_text("version: custom-v1\nentities:\n  DEFECT: [flensing]\n")
    r = parse_document(b"Zorbulator exhibits flensing.", "report.txt")[0]
    first = extraction.extract(r, pack_paths=(str(pack),))
    pack.write_text("version: custom-v1\nentities:\n  DEFECT: [otherword]\n")
    second = extraction.extract(r, pack_paths=(str(pack),))
    assert any(e.label == "DEFECT" for e in first.entities)
    assert not any(e.label == "DEFECT" for e in second.entities)
    assert (
        first.document_metadata["extractor_version"]
        != second.document_metadata["extractor_version"]
    )


def test_explicit_unfamiliar_material_and_compound_defect():
    if extraction.english_model() is None:
        return
    r = parse_document(b"The collar made of Inconel cracked at 15 um.", "new.txt")[0]
    result = extraction.extract(r)
    assert any(e.label == "MATERIAL" and e.text == "Inconel" for e in result.entities)
    assert any(e.label == "MEASUREMENT" and e.text == "15 um" for e in result.entities)
    compound = extraction.extract(parse_document(b"Ceramic spindle crack observed.", "new.txt")[0])
    assert any(e.label == "COMPONENT" and e.text == "spindle" for e in compound.entities)


def test_explicit_absence_is_not_unknown_extraction():
    result = extraction.extract(parse_document(b"No defects were found.", "clean.txt")[0])
    assert not result.findings and not result.review_candidates
    assert result.absence_statements[0].text == "No defects were found"
    mixed = extraction.extract(
        parse_document(b"No defects were found; spindle leaking.", "mixed.txt")[0]
    )
    assert mixed.absence_statements and mixed.findings[0].defect.assertion == "present"
