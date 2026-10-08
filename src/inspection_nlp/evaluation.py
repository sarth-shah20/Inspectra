"""Human-gated, vendor-independent evaluation with fixed labels and leakage checks."""

import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import spacy

from .contextual import unmatched_clauses
from .documents import parse_document
from .extraction import assertion, extract
from .findings import with_findings
from .hybrid import extract_hybrid, load_silver_ner
from .metadata import vendor_key
from .schemas import Entity, Record

LABELS = tuple(Entity.model_fields["label"].annotation.__args__)


@dataclass
class GoldExample:
    original: Record
    reference: Record
    group_id: str
    annotators: list[str]


def load_gold(path: Path, allowed_ids: set[str] | None = None) -> list[GoldExample]:
    examples = []
    seen = set()
    tokenizer = spacy.blank("en")
    with path.open() as source:
        for line in source:
            row = json.loads(line)
            raw = row["record"]
            if allowed_ids is not None and raw["record_id"] not in allowed_ids:
                continue
            if (
                not row.get("privacy_reviewed")
                or row.get("annotation_source") != "human"
                or row.get("annotation_status") != "adjudicated"
            ):
                raise ValueError("Gold records require human adjudication and privacy review")
            annotators = row.get("annotator_ids", [])
            if (
                len(set(annotators)) < 2
                or not row.get("adjudicator_id")
                or not row.get("annotation_version")
            ):
                raise ValueError(
                    "Two independent annotators, adjudicator and annotation version are required"
                )
            original = Record.model_validate(
                {
                    **raw,
                    "entities": [],
                    "findings": [],
                    "relations": [],
                    "review_candidates": [],
                    "reported_severity": None,
                }
            )
            if original.record_id in seen:
                raise ValueError("Duplicate gold record identity")
            seen.add(original.record_id)
            payload = original.model_dump()
            payload.update(
                entities=row["entities"],
                findings=row.get("findings", []),
                review_candidates=row.get("review_candidates", []),
                label_origin="human",
            )
            reference = Record.model_validate(payload)
            for entity in reference.entities:
                if entity.extraction_method != "human":
                    raise ValueError("Gold entities must have human provenance")
            ordered = sorted(reference.entities, key=lambda e: e.evidence_start)
            if any(b.evidence_start < a.evidence_end for a, b in pairwise(ordered)):
                raise ValueError("Overlapping gold spans are unsupported")
            doc = tokenizer.make_doc(reference.display_text)
            if any(
                doc.char_span(e.evidence_start, e.evidence_end, alignment_mode="strict") is None
                for e in ordered
            ):
                raise ValueError("Gold offsets must align to tokens")
            defects = {(e.evidence_start, e.evidence_end) for e in ordered if e.label == "DEFECT"}
            linked = {(f.defect.evidence_start, f.defect.evidence_end) for f in reference.findings}
            if defects != linked:
                raise ValueError(
                    "Every gold defect needs an adjudicated finding, including explicitly unlinked findings"
                )
            examples.append(
                GoldExample(
                    original,
                    reference,
                    row.get("group_id") or original.report_id or original.source_event_id,
                    annotators,
                )
            )
    return examples


def template_key(record: Record):
    text = record.display_text.casefold()
    vendor = record.report_metadata.get("vendor")
    if vendor:
        text = re.sub(r"(?<!\w)" + re.escape(vendor.casefold()) + r"(?!\w)", "<vendor>", text)
    text = re.sub(r"\d+(?:\.\d+)?", "<number>", text)
    return hashlib.sha256(" ".join(re.findall(r"\w+|<number>|<vendor>", text)).encode()).hexdigest()


def connected_groups(examples: list[GoldExample], vendor_holdout=False):
    parent = list(range(len(examples)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen, tokens = {}, []
    for i, example in enumerate(examples):
        record = example.original
        keys = [
            ("event", example.group_id),
            ("report", record.report_id or record.source_event_id),
            ("template", template_key(record)),
        ]
        vendor = vendor_key(record.report_metadata.get("vendor", ""))
        if vendor_holdout and vendor:
            keys.append(("vendor", vendor))
        for key in keys:
            if key in seen:
                parent[root(i)] = root(seen[key])
            else:
                seen[key] = i
        words = set(re.findall(r"[a-z]+", record.clean_text.casefold()))
        # Conservative near-template grouping for annotation-sized evaluation batches.
        for j, previous in enumerate(tokens):
            if (
                min(len(words), len(previous)) >= 8
                and len(words & previous) / len(words | previous) >= 0.9
            ):
                parent[root(i)] = root(j)
        tokens.append(words)
    groups = defaultdict(list)
    for i, example in enumerate(examples):
        groups[root(i)].append(example)
    return list(groups.values())


def partition(examples, mode="grouped", holdout=(), train_end=None, validation_end=None):
    if mode not in {"grouped", "vendor", "template", "industry", "temporal"}:
        raise ValueError("Unknown evaluation split mode")
    if mode in {"vendor", "template", "industry"} and not holdout:
        raise ValueError("Explicit held-out values are required")
    if mode == "temporal" and (not train_end or not validation_end or train_end >= validation_end):
        raise ValueError("Temporal cutoffs must be ordered")
    groups = connected_groups(examples, vendor_holdout=mode == "vendor")
    assignments = {}
    for group in groups:
        key = min(x.original.record_id for x in group)
        hashed = (
            int(hashlib.sha256(("generalisation-v1:" + key).encode()).hexdigest()[:8], 16) / 2**32
        )
        if mode == "temporal":
            periods = set()
            for example in group:
                date = (
                    example.original.report_metadata.get("report_date")
                    or example.original.report_date
                )
                periods.add(
                    "quarantine"
                    if not date
                    else "train"
                    if date <= train_end
                    else "validation"
                    if date <= validation_end
                    else "test"
                )
            split = periods.pop() if len(periods) == 1 else "quarantine"
        elif mode in {"vendor", "template", "industry"}:
            values = [
                vendor_key(x.original.report_metadata.get("vendor", ""))
                if mode == "vendor"
                else template_key(x.original)
                if mode == "template"
                else x.original.domain
                for x in group
            ]
            held = {vendor_key(v) for v in holdout} if mode == "vendor" else set(holdout)
            split = "test" if held & set(values) else "train" if hashed < 0.8 else "validation"
        else:
            split = "train" if hashed < 0.7 else "validation" if hashed < 0.85 else "test"
        assignments.update({x.original.record_id: split for x in group})
    if mode in {"vendor", "template", "industry"} and "test" not in assignments.values():
        raise ValueError("Held-out values do not match any report")
    return assignments


def audit_partition(examples, assignments, mode="grouped"):
    if set(assignments) != {x.original.record_id for x in examples}:
        raise ValueError("Manifest must assign every gold record exactly once")
    if set(assignments.values()) - {"train", "validation", "test", "quarantine"}:
        raise ValueError("Invalid partition name")
    for group in connected_groups(examples, vendor_holdout=mode == "vendor"):
        if len({assignments[x.original.record_id] for x in group}) != 1:
            raise ValueError("Related reports/templates or held-out vendors cross partitions")


def metrics(predicted: set, gold: set):
    correct = len(predicted & gold)
    precision = correct / len(predicted) if predicted else 0
    recall = correct / len(gold) if gold else 0
    return {
        "predicted": len(predicted),
        "reference": len(gold),
        "correct": correct,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
    }


def span_key(record_id, entity):
    return record_id, entity.evidence_start, entity.evidence_end, entity.label


def relation_keys(record):
    return {
        (
            record.record_id,
            f.defect.evidence_start,
            f.defect.evidence_end,
            label,
            e.evidence_start,
            e.evidence_end,
        )
        for f in record.findings
        for label, values in f.links.items()
        for e in values
    }


def score_predictions(examples, predictions):
    predicted, gold, pa, ga, pr, gr = set(), set(), set(), set(), set(), set()
    confusion, errors = Counter(), []
    routed, missed = 0, 0
    for example, result in zip(examples, predictions, strict=True):
        reference = example.reference
        record_id = reference.record_id
        p = {span_key(record_id, e) for e in result.entities}
        g = {span_key(record_id, e) for e in reference.entities}
        predicted |= p
        gold |= g
        gold_defects = [e for e in reference.entities if e.label == "DEFECT"]
        pred_lookup = {span_key(record_id, e): e for e in result.entities}
        pa |= {
            (*span_key(record_id, e), e.assertion) for e in result.entities if e.label == "DEFECT"
        }
        ga |= {(*span_key(record_id, e), e.assertion) for e in gold_defects}
        pr |= relation_keys(result)
        gr |= relation_keys(reference)
        for e in gold_defects:
            key = span_key(record_id, e)
            if key in pred_lookup:
                confusion[(e.assertion, pred_lookup[key].assertion)] += 1
            else:
                missed += 1
                routed += any(
                    c.evidence_start < e.evidence_end and c.evidence_end > e.evidence_start
                    for c in result.review_candidates
                )
        errors.extend(
            {
                "record_id": record_id,
                "kind": "missed_entity",
                "start": key[1],
                "end": key[2],
                "label": key[3],
            }
            for key in g - p
        )
        errors.extend(
            {
                "record_id": record_id,
                "kind": "extra_entity",
                "start": key[1],
                "end": key[2],
                "label": key[3],
            }
            for key in p - g
        )
    return {
        "records": len(examples),
        "entities": metrics(predicted, gold),
        "per_label": {
            label: metrics(
                {x for x in predicted if x[3] == label}, {x for x in gold if x[3] == label}
            )
            for label in LABELS
        },
        "joint_defect_assertion": metrics(pa, ga),
        "relationships": metrics(pr, gr),
        "assertion_confusion": [
            {"actual": a, "predicted": b, "count": n} for (a, b), n in sorted(confusion.items())
        ],
        "missed_defects": missed,
        "missed_defects_review_routed": routed,
        "review_routing_coverage": routed / missed if missed else None,
        "errors": errors,
    }


def extract_ner(record: Record, model: Path) -> Record:
    nlp = load_silver_ner(str(model))
    entities = [
        Entity(
            label=span.label_,
            text=span.text,
            evidence_start=span.start_char,
            evidence_end=span.end_char,
            assertion=assertion(record.display_text, span.start_char, span.end_char),
            confidence=0.5,
            extraction_method="ner",
        )
        for span in nlp(record.display_text).ents
    ]
    payload = record.model_dump()
    payload.update(
        entities=[e.model_dump() for e in entities],
        findings=[],
        relations=[],
        review_candidates=unmatched_clauses(record.display_text, entities),
    )
    return with_findings(Record.model_validate(payload))


def semantic_signature(record):
    return sorted(
        (e.label, " ".join(e.text.casefold().split()), e.assertion)
        for e in record.entities
        if e.label != "VENDOR"
    )


def perturbation_checks(record):
    payload = record.model_dump()
    payload.update(
        entities=[], findings=[], relations=[], review_candidates=[], clean_to_display=[]
    )
    baseline = semantic_signature(extract(Record.model_validate(payload), use_domain=False))
    payload["report_metadata"] = {**record.report_metadata, "vendor": "unseen evaluation vendor"}
    metadata_check = (
        semantic_signature(extract(Record.model_validate(payload), use_domain=False)) == baseline
    )
    payload["display_text"] = re.sub(r"[ \t]+", "  ", record.display_text)
    payload["clean_text"] = " ".join(payload["display_text"].split())
    layout_check = (
        semantic_signature(extract(Record.model_validate(payload), use_domain=False)) == baseline
    )
    vendor = record.report_metadata.get("vendor", "")
    text_check = None
    if vendor and re.search(re.escape(vendor), record.display_text, re.IGNORECASE):
        payload["display_text"] = re.sub(
            re.escape(vendor), "Unseen Vendor", record.display_text, flags=re.IGNORECASE
        )
        payload["clean_text"] = " ".join(payload["display_text"].split())
        text_check = (
            semantic_signature(extract(Record.model_validate(payload), use_domain=False))
            == baseline
        )
    return {
        "metadata_vendor_substitution": metadata_check,
        "horizontal_whitespace": layout_check,
        "textual_vendor_substitution": text_check,
    }


def evaluate_examples(examples, model: Path | None = None):
    extractors = {
        "rules": lambda r: extract(r, use_domain=False, contextual=False),
        "contextual": lambda r: extract(r, use_domain=False),
    }
    if model:
        extractors.update(
            ner=lambda r: extract_ner(r, model),
            hybrid=lambda r: extract_hybrid(
                r.model_copy(update={"domain": "general"}), model, threshold=0.5
            ),
        )
    report = {
        "scope": "Human-adjudicated English reports; metrics apply only to measured groups.",
        "label_set": list(LABELS),
        "experiments": {},
        "perturbations": [
            {"record_id": x.original.record_id, **perturbation_checks(x.original)} for x in examples
        ],
    }
    for mode, extractor in extractors.items():
        predictions, timings, failures = [], [], []
        for example in examples:
            start = time.perf_counter()
            try:
                result = extractor(example.original)
            except (ValueError, RuntimeError, OSError) as exc:
                result = example.original
                failures.append(
                    {
                        "record_id": result.record_id,
                        "format": Path(result.source_document).suffix,
                        "error": str(exc),
                    }
                )
            timings.append(
                {
                    "record_id": example.original.record_id,
                    "format": Path(example.original.source_document).suffix,
                    "seconds": time.perf_counter() - start,
                }
            )
            predictions.append(result)
        scored = score_predictions(examples, predictions)
        scored.update(processing_times=timings, failures=failures, per_group={})
        for field in ("vendor", "industry", "template", "year"):
            groups = defaultdict(list)
            for i, example in enumerate(examples):
                r = example.original
                value = (
                    r.report_metadata.get("vendor", "Unknown")
                    if field == "vendor"
                    else r.domain
                    if field == "industry"
                    else template_key(r)
                    if field == "template"
                    else (r.report_metadata.get("report_date") or r.report_date or "Unknown")[:4]
                )
                groups[value].append(i)
            scored["per_group"][field] = {
                value: score_predictions([examples[i] for i in ids], [predictions[i] for i in ids])
                for value, ids in groups.items()
            }
        report["experiments"][mode] = scored
    return report


def benchmark_parsers(manifest: list[dict]):
    output = []
    for entry in manifest:
        if not entry.get("privacy_reviewed"):
            raise ValueError("Parser benchmarks require privacy-reviewed inputs")
        path = Path(entry["path"])
        start = time.perf_counter()
        try:
            records = parse_document(path.read_bytes(), path.name, **entry.get("settings", {}))
            output.append(
                {
                    "format": path.suffix,
                    "records": len(records),
                    "error": None,
                    "seconds": time.perf_counter() - start,
                }
            )
        except (ValueError, RuntimeError, OSError) as exc:
            output.append(
                {
                    "format": path.suffix,
                    "records": 0,
                    "error": str(exc),
                    "seconds": time.perf_counter() - start,
                }
            )
    return output
