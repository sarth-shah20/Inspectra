import spacy

from inspection_nlp.documents import parse_document
from inspection_nlp.hybrid import extract_hybrid, load_silver_ner


def test_hybrid_adds_non_overlapping_silver_ner_span(tmp_path, monkeypatch):
    monkeypatch.setattr("inspection_nlp.extraction.english_model", lambda: None)
    model = spacy.blank("en")
    ruler = model.add_pipe("entity_ruler")
    ruler.add_patterns([{"label": "COMPONENT", "pattern": "zorbulator"}])
    path = tmp_path / "silver-model"
    model.to_disk(path)
    item = parse_document(b"The zorbulator is cracked.", "note.txt")[0]
    result = extract_hybrid(item, path, threshold=0.5)
    assert [(entity.text, entity.extraction_method) for entity in result.entities] == [
        ("zorbulator", "ner"),
        ("cracked", "ruler"),
    ]
    assert result.document_metadata["hybrid_model_provenance"] == "ai_silver_labels_not_human_validated"
    load_silver_ner.cache_clear()
