"""Local, append-only storage for human corrections to extracted findings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from .schemas import Entity, Record


def human_entities(record: Record, rows: list[dict]) -> list[Entity]:
    """Validate user-edited offsets and make their provenance explicit."""
    entities = []
    for row in rows:
        start, end = int(row["evidence_start"]), int(row["evidence_end"])
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


def review_payload(record: Record, edited_rows: list[dict], note: str) -> dict:
    corrected = human_entities(record, edited_rows)
    return {
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
