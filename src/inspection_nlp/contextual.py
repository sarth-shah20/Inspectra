"""Generic syntax-assisted coverage. The English model is not a defect classifier."""

import re
from functools import lru_cache

import spacy

ENGLISH_MODEL = "en_core_web_sm"
ENGLISH_VERSION = "3.8.0"
CLAUSES = re.compile(
    r"(?<!\d)[.!?;]|\n|\b(?:but|however|although)\b|\band\b(?=\s+(?:the\s+)?\w+\s+(?:is|was|has|were|exhibits|shows))",
    re.IGNORECASE,
)
INSPECTION_CUE = re.compile(
    r"\b(?:inspect\w*|observ\w*|detect\w*|exhibits|shows|found|repair\w*|replace\w*|reject\w*|abnormal\w*|nonconform\w*)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def english_model():
    try:
        nlp = spacy.load(ENGLISH_MODEL, disable=["ner"])
        if nlp.meta.get("version") != ENGLISH_VERSION:
            return None
        return nlp
    except (OSError, ImportError, ValueError):
        return None


def clauses(text: str):
    start = 0
    for boundary in CLAUSES.finditer(text):
        if text[start : boundary.start()].strip():
            yield start, boundary.start()
        start = boundary.end()
    if text[start:].strip():
        yield start, len(text)


def contextual_components(text: str, entities: list, nlp) -> list[tuple]:
    candidates = []
    if nlp is None:
        return candidates
    for start, end in clauses(text):
        defects = [e for e in entities if e.label == "DEFECT" and start <= e.evidence_start < end]
        if not defects:
            continue
        doc = nlp(text[start:end])
        for chunk in doc.noun_chunks:
            if chunk.root.dep_ not in {"nsubj", "nsubjpass", "dobj", "pobj", "conj"}:
                continue
            if chunk.root.lemma_.lower() in {
                "inspection",
                "report",
                "finding",
                "inspector",
                "operator",
                "vendor",
                "supplier",
            }:
                continue
            if (
                chunk.root.dep_ == "nsubj"
                and chunk.root.head.lemma_.casefold()
                in {"find", "observe", "detect", "inspect", "report", "note", "document"}
                and not any(
                    e.label == "DEFECT"
                    and start + chunk.start_char <= e.evidence_start < start + chunk.end_char
                    for e in entities
                )
            ):
                continue
            # Existing material/defect evidence must not become a component span.
            tokens = [
                t
                for t in chunk
                if t.pos_ in {"NOUN", "PROPN", "ADJ"}
                and not any(
                    t.idx + start < e.evidence_end and t.idx + start + len(t) > e.evidence_start
                    for e in entities
                )
            ]
            if not tokens:
                continue
            first, last = tokens[0], tokens[-1]
            if last.i - first.i + 1 != len(tokens):
                continue
            a, b = start + first.idx, start + last.idx + len(last)
            if (a and text[a - 1] in "</") or (b < len(text) and text[b] == ">"):
                continue
            if min(min(abs(a - e.evidence_end), abs(b - e.evidence_start)) for e in defects) > 100:
                continue
            candidates.append((a, b, "COMPONENT", "contextual", 0.6))
    return candidates


def unmatched_clauses(text: str, entities: list) -> list[dict]:
    candidates = []
    for start, end in clauses(text):
        clause = text[start:end]
        if INSPECTION_CUE.search(clause) and not any(
            e.label == "DEFECT" and start <= e.evidence_start < end for e in entities
        ):
            left = len(clause) - len(clause.lstrip())
            right = len(clause.rstrip())
            candidates.append(
                {
                    "text": clause.strip(),
                    "evidence_start": start + left,
                    "evidence_end": start + right,
                    "reason": "Inspection or action clause without a supported defect",
                }
            )
    return candidates


def contextual_materials(text: str, entities: list, nlp) -> list[tuple]:
    if nlp is None:
        return []
    candidates = []
    for start, end in clauses(text):
        clause = text[start:end]
        for cue in re.finditer(
            r"\b(?:made of|constructed from|material\s*:)\s+", clause, re.IGNORECASE
        ):
            remainder = nlp(clause[cue.end() :])
            chunk = next(iter(remainder.noun_chunks), None)
            if chunk is not None and chunk.start == 0:
                a = start + cue.end() + chunk.start_char
                b = start + cue.end() + chunk.end_char
                if not any(a < e.evidence_end and b > e.evidence_start for e in entities):
                    candidates.append((a, b, "MATERIAL", "contextual", 0.6))
    return candidates
