"""Evidence exports with provenance, relationships, and safe spreadsheet values."""

import csv
import html
import io
import json

from .schemas import Record

EXPORT_VERSION = 'inspectra-export-v2'


def highlight(record: Record) -> str:
    chunks, cursor = [], 0
    for entity in sorted(record.entities, key=lambda e: e.evidence_start):
        chunks.append(html.escape(record.display_text[cursor:entity.evidence_start]))
        title = html.escape(f'{entity.label} · {entity.assertion}', quote=True)
        chunks.append(f'<mark title="{title}">{html.escape(entity.text)}</mark>')
        cursor = entity.evidence_end
    chunks.append(html.escape(record.display_text[cursor:]))
    return ''.join(chunks)


def export_json(records: list[Record], *, versioned: bool = False) -> str:
    values = [r.model_dump() for r in records]
    payload = {'export_schema_version': EXPORT_VERSION, 'records': values} if versioned else values
    return json.dumps(payload, ensure_ascii=False, indent=2)


def spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export_csv(records: list[Record]) -> str:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['record_id', 'domain', 'mapping_status', 'label', 'text', 'assertion',
        'start', 'end', 'confidence', 'method', 'report_id', 'source_document', 'vendor',
        'report_number', 'report_date', 'product', 'batch', 'asset_id', 'workflow',
        'run_id', 'review_version', 'extractor_version', 'score_kind', 'finding_ids',
        'categories', 'priorities', 'priority_reasons', 'linked_evidence', 'metadata_provenance',
        'quality_flags', 'export_schema_version'])
    for record in records:
        base = [record.record_id, record.domain, record.mapping_status]
        metadata = [record.report_id, record.source_document,
                    *(record.report_metadata.get(field, '') for field in
                      ('vendor', 'report_number', 'report_date', 'product', 'batch', 'asset_id')),
                    record.report_status or 'pending', record.document_metadata.get('run_id', ''),
                    record.document_metadata.get('review_version', ''),
                    record.document_metadata.get('extractor_version', ''),
                    record.document_metadata.get('confidence_kind', 'uncalibrated')]
        for entity in record.entities or [None]:
            evidence = [entity.label, entity.text, entity.assertion, entity.evidence_start,
                entity.evidence_end, entity.confidence, entity.extraction_method] if entity else [''] * 7
            matched = [f for f in record.findings if entity and any(
                entity.label == e.label and entity.evidence_start == e.evidence_start and entity.evidence_end == e.evidence_end
                for e in [f.defect, *(e for values in f.links.values() for e in values)])]
            extra = ['; '.join(f.finding_id for f in matched), '; '.join(f.category or 'Uncategorized' for f in matched),
                '; '.join(f.priority for f in matched), '; '.join(reason for f in matched for reason in f.priority_reasons),
                json.dumps({f.finding_id: {label: [e.model_dump() for e in values] for label, values in f.links.items()} for f in matched}),
                json.dumps(record.metadata_provenance), '; '.join(record.quality_flags), EXPORT_VERSION]
            writer.writerow([spreadsheet_safe(value) for value in base + evidence + metadata + extra])
    return stream.getvalue()


def export_html(records: list[Record]) -> str:
    from .analytics import finding_rows, overview, vendor_rates
    rows = finding_rows(records)
    summary = overview(records, rows)
    sections = []
    for record in records:
        findings = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in
            [f.defect.text, f.category or 'Uncategorized', f.defect.assertion, f.priority,
             '; '.join(f.priority_reasons), json.dumps({label: [e.text for e in values] for label, values in f.links.items()})]) + '</tr>' for f in record.findings)
        sections.append(f'<section><h2>{html.escape(record.source_document)}</h2>'
            f'<p>{html.escape(json.dumps(record.report_metadata))}</p>'
            f'<p>Run: {html.escape(record.document_metadata.get("run_id", "unknown"))} · '
            f'Review: {html.escape(record.document_metadata.get("review_version", "original"))}</p>'
            f'<table><thead><tr><th>Defect</th><th>Category</th><th>Assertion</th><th>Priority</th><th>Reasons</th><th>Linked evidence</th></tr></thead><tbody>{findings}</tbody></table>'
            f'<div class="evidence">{highlight(record)}</div>'
            f'<p>Quality flags: {html.escape(", ".join(record.quality_flags) or "None")}</p></section>')
    rates = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in row.values()) + '</tr>' for row in vendor_rates(records, rows))
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Inspectra inspection summary</title>' + '''<style>
body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#163234}
section{border-top:1px solid #ccc;padding:20px 0}table{border-collapse:collapse;width:100%;margin:16px 0}
th,td{border:1px solid #ddd;padding:8px;text-align:left;overflow-wrap:anywhere}mark{background:#fff0a8}
.evidence{white-space:pre-wrap;padding:16px;background:#f3f7f7}h1,h2{color:#176969}</style>''' + f'<body><h1>Inspectra inspection summary</h1><p>{html.escape(json.dumps(summary))}</p>' + \
        '<p>English vendor-report evidence. Review priorities are workflow aids. Scores are uncalibrated; generalisation accuracy awaits human validation.</p>' + \
        '<table><thead><tr><th>Vendor</th><th>Inspected reports</th><th>Affected reports</th><th>Affected-report rate (%)</th></tr></thead><tbody>' + rates + '</tbody></table>' + \
        ''.join(sections) + f'<footer>{EXPORT_VERSION}</footer></body></html>'
