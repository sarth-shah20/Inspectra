"""Build clean-text-only, privacy-screened AI silver annotations."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

import spacy

from inspection_nlp.data_quality import fingerprint
from inspection_nlp.extraction import extract
from inspection_nlp.preprocessing import REDACTORS, prepare_text
from inspection_nlp.schemas import Record

QUOTAS = {"train": {"construction": 67, "aviation": 67, "pipeline": 66},
          "validation": {"construction": 17, "aviation": 17, "pipeline": 16},
          "test": {"construction": 25, "aviation": 25, "pipeline": 25}}
RISKS = {
    "email": REDACTORS[0], "phone": REDACTORS[1], "coordinates": REDACTORS[2],
    "named_coordinates": REDACTORS[3], "street_address": REDACTORS[4],
    "registration_number": re.compile(r"\b(?:N\d{1,5}[A-Z]{0,2}|[A-Z]{1,3}-\d{2,6})\b"),
    "personal_name": re.compile(r"\b(?:mr\.?|mrs\.?|ms\.?|dr\.?|inspector|reported by|contact)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b", re.IGNORECASE),
}
ALLOWED = {"VENDOR", "PRODUCT", "COMPONENT", "MATERIAL", "DEFECT", "LOCATION", "MEASUREMENT", "INSPECTION_METHOD", "REPORTED_SEVERITY", "CAUSE", "CORRECTIVE_ACTION", "DATE"}

def partition(domain, grouped, temporal, official_safe):
    value = official_safe if domain == "construction" else temporal if domain == "aviation" else grouped
    return value if value in QUOTAS else None

def risks(text):
    found = [name for name, pattern in RISKS.items() if pattern.search(text)]
    _, changed = prepare_text(text)
    return sorted(set(found + (["detector_redaction_change"] if changed else [])))

def candidates(snapshot):
    db = sqlite3.connect(f"file:{(snapshot / 'index.sqlite').resolve()}?mode=ro", uri=True)
    split_case = "CASE WHEN domain='construction' THEN official_safe WHEN domain='aviation' THEN temporal WHEN domain='pipeline' THEN grouped END"
    query = f"""WITH base AS (SELECT record_id,domain,label,group_id,sample_rank,{split_case} AS split FROM records WHERE excluded='' AND label!=''), safe AS (SELECT group_id FROM base WHERE split IN ('train','validation','test') GROUP BY group_id HAVING COUNT(DISTINCT split)=1), representatives AS (SELECT record_id,domain,label,group_id,split,sample_rank,ROW_NUMBER() OVER (PARTITION BY domain,group_id ORDER BY sample_rank) AS group_rank FROM base WHERE split IN ('train','validation','test') AND group_id IN safe), one_per_group AS (SELECT * FROM representatives WHERE group_rank=1), labels AS (SELECT domain,split,label,ROW_NUMBER() OVER (PARTITION BY domain,split ORDER BY COUNT(*) DESC,label) AS label_rank FROM one_per_group GROUP BY domain,split,label), ranked AS (SELECT record_id,domain,label,group_id,split,sample_rank,ROW_NUMBER() OVER (PARTITION BY domain,split,label ORDER BY sample_rank) AS sample_rank_in_label FROM one_per_group) SELECT r.record_id,r.domain,r.label,r.group_id,r.split,r.sample_rank FROM ranked r JOIN labels l ON (r.domain,r.split,r.label)=(l.domain,l.split,l.label) WHERE l.label_rank<=10 AND r.sample_rank_in_label<=300"""
    try:
        return [{"record_id": record_id, "domain": domain, "source_label": label, "group_id": group_id, "split": split, "rank": rank or fingerprint("silver-v1:" + record_id)} for record_id, domain, label, group_id, split, rank in db.execute(query)]
    finally:
        db.close()
def select(rows):
    chosen = []
    for split, per_domain in QUOTAS.items():
        for domain, quota in per_domain.items():
            strata = defaultdict(list)
            for row in rows:
                if row["split"] == split and row["domain"] == domain: strata[row["source_label"]].append(row)
            groups = sorted(strata.items())
            base, extra = divmod(quota, len(groups))
            picks = []
            for index, (_, group) in enumerate(groups): picks += sorted(group, key=lambda x: x["rank"])[:base + (index < extra)]
            seen = {row["record_id"] for row in picks}
            picks += sorted((row for group in strata.values() for row in group if row["record_id"] not in seen), key=lambda x: (x["rank"], x["source_label"]))[:quota-len(picks)]
            if len(picks) != quota: raise ValueError(f"insufficient eligible {domain}/{split} records")
            chosen += picks
    return chosen

def label(row, text):
    record = Record(record_id=row["record_id"], source_dataset="silver", source_record_id=row["record_id"], source_event_id=row["group_id"], source_document="cleaned", source_sha256="silver", source_row=2, domain=row["domain"], schema_version="silver-v1", source_column_mapping={}, clean_text=text, display_text=text, label_origin="weak")
    tokenizer = spacy.blank("en")
    entities = [entity.model_dump() for entity in extract(record).entities]
    entities = [entity for entity in entities if tokenizer.make_doc(text).char_span(entity["evidence_start"], entity["evidence_end"], entity["label"], alignment_mode="strict") is not None]
    return {"record_id": row["record_id"], "domain": row["domain"], "split": row["split"], "group_id": row["group_id"], "source_label": row["source_label"], "clean_text": text, "entities": entities, "annotation_source": "ai", "annotation_status": "ai_annotated", "label_origin": "silver", "annotation_version": "silver-rules-v1"}

def validate(rows):
    errors, ids, groups = [], set(), {}
    for row in rows:
        if row["record_id"] in ids: errors.append("duplicate record_id")
        ids.add(row["record_id"])
        if groups.setdefault(row["group_id"], row["split"]) != row["split"]: errors.append("group crosses split")
        entities = sorted(row["entities"], key=lambda x: (x["evidence_start"], x["evidence_end"]))
        for a, b in pairwise(entities):
            if b["evidence_start"] < a["evidence_end"]: errors.append(f"overlap:{row['record_id']}")
        for entity in entities:
            if entity["label"] not in ALLOWED: errors.append(f"label:{row['record_id']}")
            if row["clean_text"][entity["evidence_start"]:entity["evidence_end"]] != entity["text"]: errors.append(f"offset:{row['record_id']}")
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/processed/corpus-v1"))
    parser.add_argument("--output", type=Path, default=Path("data/annotations/ai_annotated.jsonl"))
    parser.add_argument("--review-queue", type=Path, default=Path("data/annotations/review_queue.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("reports/silver_annotation_report.json"))
    args = parser.parse_args()
    if any(path.exists() for path in (args.output, args.review_queue, args.report)): parser.error("refusing to overwrite artifacts")
    all_candidates = candidates(args.snapshot)
    selected = select(all_candidates)
    selected_ids = {row["record_id"] for row in selected}
    by_id = {row["record_id"]: row for row in all_candidates}
    needs = Counter()
    exclusions, replacements = [], defaultdict(list)
    with (args.snapshot / "cleaned.jsonl").open() as source:
        for line in source:
            value = json.loads(line); record_id = value["record_id"]
            row = by_id.get(record_id)
            if row is None: continue
            risk = risks(value["clean_text"])
            key = (row["split"], row["domain"], row["source_label"])
            if record_id in selected_ids and risk:
                exclusions.append({**row, "privacy_risks": risk}); needs[key] -= 1
            elif record_id not in selected_ids and not risk and len(replacements[key]) < max(0, -needs[key]):
                replacements[key].append((row, value["clean_text"]))
    for key, remaining in needs.items():
        if remaining < 0 and len(replacements[key]) < -remaining: raise ValueError(f"no privacy-safe replacement for {key}")
    text_by_id = {}
    for row in selected:
        if not any(item["record_id"] == row["record_id"] for item in exclusions): text_by_id[row["record_id"]] = None
    selected = [row for row in selected if row["record_id"] not in {item["record_id"] for item in exclusions}]
    for values in replacements.values():
        for row, text in values: selected.append(row); text_by_id[row["record_id"]] = text
    wanted = {row["record_id"] for row in selected if text_by_id.get(row["record_id"]) is None}
    with (args.snapshot / "cleaned.jsonl").open() as source:
        for line in source:
            value = json.loads(line)
            if value["record_id"] in wanted: text_by_id[value["record_id"]] = value["clean_text"]
    if len(selected) != 325 or any(text_by_id[row["record_id"]] is None for row in selected): raise ValueError("privacy replacement or cleaned text lookup failed")
    excluded = exclusions
    annotations = [label(row, text_by_id[row["record_id"]]) for row in selected]
    errors = validate(annotations)
    if errors: raise ValueError("validation failed: " + "; ".join(errors[:10]))
    # Second independent integrity pass queues cases that rule labels cannot resolve confidently.
    queue = []
    for row in annotations:
        reasons = ([] if row["entities"] else ["no_entities"])
        if any(entity["assertion"] != "present" for entity in row["entities"]): reasons.append("non_present_assertion")
        if any(entity["confidence"] < .9 for entity in row["entities"]): reasons.append("dictionary_match")
        if reasons: queue.append({**row, "review_reasons": reasons})
    for path, rows in ((args.output, annotations), (args.review_queue, queue)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as target:
            for row in rows: target.write(json.dumps(row) + "\n")
    report = {"artifact": "AI-generated silver annotations; not human-reviewed, privacy-approved, adjudicated, or gold.", "records_per_domain_and_split": {split: dict(Counter(row["domain"] for row in annotations if row["split"] == split)) for split in QUOTAS}, "entities_per_label": dict(Counter(entity["label"] for row in annotations for entity in row["entities"])), "excluded_privacy_risk_records": excluded, "records_with_no_entities": [row["record_id"] for row in annotations if not row["entities"]], "validation_errors": errors, "uncertain_annotations_requiring_review": len(queue), "total_records": len(annotations)}
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"records": len(annotations), "excluded": len(excluded), "uncertain": len(queue)}))
if __name__ == "__main__": main()
