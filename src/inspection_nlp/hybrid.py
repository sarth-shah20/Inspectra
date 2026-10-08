"""Optional hybrid extraction with rules preferred over provisional silver NER spans."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import spacy

from .extraction import assertion, extract
from .schemas import Entity, Record


@lru_cache(maxsize=2)
def load_silver_ner(model_path: str):
    """Load a local model artifact; callers choose whether it is appropriate to use."""
    return spacy.load(model_path)


def extract_hybrid(record: Record, model_path: Path, *, threshold: float = 0.5, contextual: bool = True, pack_paths: tuple[str, ...] = ()) -> Record:
    """Merge strict-token NER spans into rules without replacing deterministic evidence."""
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between zero and one")
    result = extract(record, contextual=contextual, pack_paths=pack_paths)
    nlp = load_silver_ner(str(model_path))
    entities = [entity for entity in result.entities if entity.confidence >= threshold]
    for span in nlp(record.display_text).ents:
        if 0.5 < threshold:
            continue
        start, end = span.start_char, span.end_char
        if any(start < entity.evidence_end and end > entity.evidence_start for entity in entities):
            continue
        entities.append(
            Entity(
                label=span.label_,
                text=record.display_text[start:end],
                evidence_start=start,
                evidence_end=end,
                assertion=assertion(record.display_text, start, end),
                confidence=0.5,
                extraction_method="ner",
            )
        )
    entities.sort(key=lambda entity: entity.evidence_start)
    payload = result.model_dump()
    metadata = dict(result.document_metadata)
    metadata.update(
        hybrid_model=str(model_path),
        hybrid_policy="all-candidates-threshold-v2",
        hybrid_model_provenance="ai_silver_labels_not_human_validated",
        hybrid_threshold=str(threshold),
        confidence_kind="uncalibrated_rule_and_silver_ner_scores",
        review_reason="Silver NER spans and rule assertions require human review",
    )
    defects = [entity for entity in entities if entity.label == "DEFECT"]
    payload.update(
        entities=[entity.model_dump() for entity in entities],
        document_metadata=metadata,
        mapping_status="review_required" if defects or result.review_candidates else "unmapped",
        assertion_status=next(iter({entity.assertion for entity in defects})) if len({entity.assertion for entity in defects}) == 1 else "unknown",
        reported_severity="; ".join(dict.fromkeys(e.text for e in entities if e.label == "REPORTED_SEVERITY" and e.assertion == "present")) or None,
    )
    return Record.model_validate(payload)
