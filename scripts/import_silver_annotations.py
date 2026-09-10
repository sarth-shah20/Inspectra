"""Validate silver annotations and write separate, non-gold spaCy artifacts."""
from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path

import spacy
from spacy.tokens import DocBin

from inspection_nlp.schemas import Entity


def run(source, output, sidecar):
    nlp = spacy.blank("en"); docs = DocBin(store_user_data=False); attrs = []
    for number, line in enumerate(source.open(), 1):
        row = json.loads(line)
        if row.get("annotation_source") != "ai" or row.get("annotation_status") != "ai_annotated" or row.get("label_origin") != "silver": raise ValueError(f"line {number}: silver provenance required")
        text = row.get("clean_text")
        if not isinstance(text, str) or not text: raise ValueError(f"line {number}: clean_text required")
        entities = sorted([Entity.model_validate(x) for x in row.get("entities", [])], key=lambda e: (e.evidence_start, e.evidence_end))
        for left, right in pairwise(entities):
            if right.evidence_start < left.evidence_end: raise ValueError(f"line {number}: overlap")
        doc = nlp.make_doc(text); spans=[]
        for entity in entities:
            if text[entity.evidence_start:entity.evidence_end] != entity.text: raise ValueError(f"line {number}: offset mismatch")
            span=doc.char_span(entity.evidence_start, entity.evidence_end, entity.label, alignment_mode="strict")
            if span is None: raise ValueError(f"line {number}: token boundary")
            spans.append(span)
        doc.ents=spans; docs.add(doc); attrs.append({"record_id":row["record_id"], "split":row["split"], "domain":row["domain"], "entities":[{"label":e.label,"start":e.evidence_start,"end":e.evidence_end,"assertion":e.assertion} for e in entities], "annotation_source":"ai", "annotation_status":"ai_annotated", "label_origin":"silver"})
    output.parent.mkdir(parents=True, exist_ok=True); docs.to_disk(output); sidecar.write_text(json.dumps(attrs, indent=2)+"\n"); return len(attrs)
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,default=Path("data/annotations/silver.spacy")); p.add_argument("--sidecar",type=Path,default=Path("data/annotations/silver_attributes.json")); a=p.parse_args()
    if a.output.exists() or a.sidecar.exists(): p.error("refusing to overwrite silver artifacts")
    print(json.dumps({"records":run(a.input,a.output,a.sidecar),"artifact":"silver; not gold"}))
if __name__ == "__main__": main()
