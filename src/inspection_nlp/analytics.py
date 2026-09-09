"""Dashboard-ready summaries over canonical extracted records."""

from collections import Counter

from .schemas import Record


def entity_counts(records: list[Record]) -> list[dict[str, int | str]]:
    counts = Counter(entity.label for record in records for entity in record.entities)
    return [{"entity": label, "count": count} for label, count in sorted(counts.items())]


def review_summary(records: list[Record]) -> dict[str, int]:
    return {
        "records": len(records),
        "entities": sum(len(record.entities) for record in records),
        "review_required": sum(record.mapping_status == "review_required" for record in records),
        "unmapped": sum(record.mapping_status == "unmapped" for record in records),
    }
