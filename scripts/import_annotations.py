"""Validate reviewed JSONL annotations and write spaCy DocBin plus an attribute sidecar."""

from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path

import spacy
from spacy.tokens import DocBin

from inspection_nlp.schemas import Entity


def import_annotations(source: Path, output: Path, sidecar: Path) -> int:
    """Import explicit non-overlapping spans; no model predictions enter the gold artifact."""
    nlp = spacy.blank("en")
    docs = DocBin(store_user_data=False)
    attributes = []
    with source.open() as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            text = row.get("text", "")
            if not isinstance(text, str) or not text:
                raise ValueError(f"Line {line_number}: non-empty text is required")
            entity_rows = row.get("entities", row.get("corrected_entities"))
            if entity_rows is None:
                raise ValueError(f"Line {line_number}: entities are required")
            if row.get("annotation_status") not in {"complete", "adjudicated"}:
                raise ValueError(
                    f"Line {line_number}: annotation_status must be complete or adjudicated"
                )
            parsed = [Entity.model_validate(entity) for entity in entity_rows]
            parsed.sort(key=lambda entity: (entity.evidence_start, entity.evidence_end))
            for previous, current in pairwise(parsed):
                if current.evidence_start < previous.evidence_end:
                    raise ValueError(f"Line {line_number}: overlapping entities are unsupported")
            doc = nlp.make_doc(text)
            spans = []
            for entity in parsed:
                if text[entity.evidence_start : entity.evidence_end] != entity.text:
                    raise ValueError(f"Line {line_number}: evidence does not match text")
                span = doc.char_span(
                    entity.evidence_start,
                    entity.evidence_end,
                    entity.label,
                    alignment_mode="strict",
                )
                if span is None:
                    raise ValueError(
                        f"Line {line_number}: entity boundaries do not align to spaCy tokens"
                    )
                spans.append(span)
            doc.ents = spans
            docs.add(doc)
            attributes.append(
                {
                    "record_id": row.get("record_id"),
                    "domain": row.get("domain"),
                    "entities": [
                        {
                            "label": entity.label,
                            "start": entity.evidence_start,
                            "end": entity.evidence_end,
                            "assertion": entity.assertion,
                        }
                        for entity in parsed
                    ],
                    "label_origin": "human",
                    "annotation_status": row["annotation_status"],
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    docs.to_disk(output)
    sidecar.write_text(json.dumps(attributes, indent=2) + "\n")
    return len(attributes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/annotations/gold.spacy"))
    parser.add_argument(
        "--sidecar", type=Path, default=Path("data/annotations/gold_attributes.json")
    )
    args = parser.parse_args()
    if args.output.exists() or args.sidecar.exists():
        parser.error("Refusing to overwrite annotation artifacts; choose new output paths")
    count = import_annotations(args.input, args.output, args.sidecar)
    print(json.dumps({"records": count, "output": str(args.output), "sidecar": str(args.sidecar)}))


if __name__ == "__main__":
    main()
