"""Local, append-only storage for human corrections to extracted findings."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from .schemas import Entity, Record
from .findings import edit_relationships, with_findings


def human_entities(record: Record, rows: list[dict]) -> list[Entity]:
    """Validate user-edited offsets and make their provenance explicit."""
    entities = []
    for row in rows:
        start, end = int(row["evidence_start"]), int(row["evidence_end"])
        if start < 0 or end > len(record.display_text) or end <= start:
            raise ValueError("Evidence offsets must be within the narrative")
        entity = Entity(
            label=row["label"],
            text=record.display_text[start:end],
            evidence_start=start,
            evidence_end=end,
            assertion=row["assertion"],
            confidence=1.0,
            extraction_method="human",
        )
        if not entity.text:
            raise ValueError("Evidence span cannot be empty")
        entities.append(entity)
    entities.sort(key=lambda entity: (entity.evidence_start, entity.evidence_end))
    for previous, current in pairwise(entities):
        if current.evidence_start < previous.evidence_end:
            raise ValueError("Human-reviewed entities cannot overlap")
    return entities


def review_payload(record: Record, edited_rows: list[dict], note: str, relationship_edits: list[dict] | None = None) -> dict:
    corrected = human_entities(record, edited_rows)
    payload = record.model_dump()
    payload.update(entities=[e.model_dump() for e in corrected], findings=[], relations=[])
    reviewed = with_findings(Record.model_validate(payload))
    if relationship_edits is not None:
        reviewed = edit_relationships(reviewed, relationship_edits)
    return {
        "corrected_findings": [f.model_dump() for f in reviewed.findings],
        "reviewed_at": datetime.now(UTC).isoformat(),
        "record_id": record.record_id,
        "source_dataset": record.source_dataset,
        "source_record_id": record.source_record_id,
        "domain": record.domain,
        "display_text": record.display_text,
        "original_entities": [entity.model_dump() for entity in record.entities],
        "corrected_entities": [entity.model_dump() for entity in corrected],
        "note": note.strip(),
        "label_origin": "human",
    }


def append_review(path: Path, payload: dict) -> None:
    """Append without touching raw or generated source records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as target:
        target.write(json.dumps(payload, ensure_ascii=False) + "\n")


def review_history(path: Path) -> list[dict]:
    """Read append-only review history; malformed lines are rejected rather than hidden."""
    if not path.exists():
        return []
    history = []
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid review JSON on line {line_number}") from exc
            required = {"reviewed_at", "record_id", "domain", "corrected_entities", "note"}
            if not required <= set(row):
                raise ValueError(f"Incomplete review on line {line_number}")
            history.append(row)
    return sorted(history, key=lambda row: row["reviewed_at"], reverse=True)


def review_analytics(history: list[dict]) -> dict:
    """Aggregate reviewer changes without exposing reviewed narrative text."""
    original_labels, corrected_labels, assertions = Counter(), Counter(), Counter()
    outcomes, correction_types, confidence = Counter(), Counter(), {
        "0–49%": [0, 0], "50–74%": [0, 0], "75–94%": [0, 0], "95–100%": [0, 0]
    }
    for review in history:
        original = review["original_entities"]
        corrected = review["corrected_entities"]
        original_labels.update(entity["label"] for entity in original)
        corrected_labels.update(entity["label"] for entity in corrected)
        assertions.update(entity["assertion"] for entity in corrected)
        original_keys = {
            (item["evidence_start"], item["evidence_end"], item["label"], item["assertion"])
            for item in original
        }
        corrected_keys = {
            (item["evidence_start"], item["evidence_end"], item["label"], item["assertion"])
            for item in corrected
        }
        outcomes["Confirmed"] += len(original_keys & corrected_keys)
        outcomes["Removed or changed"] += len(original_keys - corrected_keys)
        outcomes["Added or changed"] += len(corrected_keys - original_keys)
        corrected_boundaries = {(item["evidence_start"], item["evidence_end"]) for item in corrected}
        original_boundaries = {(item["evidence_start"], item["evidence_end"]) for item in original}
        for entity in original:
            key = (entity["evidence_start"], entity["evidence_end"], entity["label"], entity["assertion"])
            if key in corrected_keys:
                action = "Confirmed"
            elif (entity["evidence_start"], entity["evidence_end"]) in corrected_boundaries:
                action = "Label or status changed"
            else:
                action = "Removed or boundary changed"
            correction_types[action] += 1
            score = entity["confidence"]
            band = "0–49%" if score < 0.5 else "50–74%" if score < 0.75 else "75–94%" if score < 0.95 else "95–100%"
            confidence[band][0] += 1
            confidence[band][1] += action == "Confirmed"
        correction_types["Added"] += len(corrected_boundaries - original_boundaries)
    return {
        "outcomes": dict(outcomes),
        "correction_types": dict(correction_types),
        "before_after": {"Initial": dict(original_labels), "Reviewed": dict(corrected_labels)},
        "assertions": dict(assertions),
        "confidence": [
            {"band": band, "findings": total, "confirmed": confirmed,
             "confirmation_rate": round(confirmed / total * 100, 1) if total else 0}
            for band, (total, confirmed) in confidence.items() if total
        ],
    }
