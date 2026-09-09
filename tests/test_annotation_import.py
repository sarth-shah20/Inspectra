import json
import runpy

import pytest
from spacy.tokens import DocBin

from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract
from inspection_nlp.reviews import review_payload

namespace = runpy.run_path("scripts/import_annotations.py")
import_annotations = namespace["import_annotations"]


def annotated_row():
    record = extract(parse_document(b"Valve crack found.", "note.txt", domain="pipeline")[0])
    payload = review_payload(
        record, [entity.model_dump() for entity in record.entities], "Reviewed"
    )
    payload["text"] = payload.pop("display_text")
    payload["entities"] = payload.pop("corrected_entities")
    payload["annotation_status"] = "adjudicated"
    return payload


def test_import_creates_docbin_and_assertion_sidecar(tmp_path):
    source = tmp_path / "annotations.jsonl"
    source.write_text(json.dumps(annotated_row()) + "\n")
    output, sidecar = tmp_path / "gold.spacy", tmp_path / "attributes.json"
    assert import_annotations(source, output, sidecar) == 1
    docs = list(DocBin().from_disk(output).get_docs(__import__("spacy").blank("en").vocab))
    assert [(entity.text, entity.label_) for entity in docs[0].ents] == [
        ("Valve", "COMPONENT"),
        ("crack", "DEFECT"),
    ]
    assert json.loads(sidecar.read_text())[0]["entities"][1]["assertion"] == "present"


def test_import_rejects_bad_evidence(tmp_path):
    row = annotated_row()
    row["entities"][0]["text"] = "wrong"
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="evidence"):
        import_annotations(source, tmp_path / "out.spacy", tmp_path / "sidecar.json")
