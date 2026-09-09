"""Exports contain displayed evidence; source targets remain separate."""

import csv
import html
import io
import json

from .schemas import Record


def highlight(record: Record) -> str:
    chunks, cursor = [], 0
    for entity in sorted(record.entities, key=lambda e: e.evidence_start):
        chunks.append(html.escape(record.display_text[cursor : entity.evidence_start]))
        title = html.escape(f"{entity.label} · {entity.assertion}", quote=True)
        chunks.append(f'<mark title="{title}">{html.escape(entity.text)}</mark>')
        cursor = entity.evidence_end
    chunks.append(html.escape(record.display_text[cursor:]))
    return "".join(chunks)


def export_json(records: list[Record]) -> str:
    return json.dumps([r.model_dump() for r in records], ensure_ascii=False, indent=2)


def export_csv(records: list[Record]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "record_id",
            "domain",
            "mapping_status",
            "label",
            "text",
            "assertion",
            "start",
            "end",
            "confidence",
            "method",
        ]
    )

    def safe(value):
        # Neutralize formula-like user text when opened in spreadsheet software.
        return (
            "'" + value
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
            else value
        )

    for record in records:
        base = [record.record_id, record.domain, record.mapping_status]
        for entity in record.entities:
            writer.writerow(
                [
                    safe(v)
                    for v in base
                    + [
                        entity.label,
                        entity.text,
                        entity.assertion,
                        entity.evidence_start,
                        entity.evidence_end,
                        entity.confidence,
                        entity.extraction_method,
                    ]
                ]
            )
        if not record.entities:
            writer.writerow(base + [""] * 7)
    return stream.getvalue()
