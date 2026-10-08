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


def report_key(record: Record) -> str:
    return record.report_id or record.record_id


def scope_records(records: list[Record], filters: dict) -> list[Record]:
    """Metadata scope defines inspected-report denominators independently of defect filters."""
    output = []
    for record in records:
        values = {'vendor': record.report_metadata.get('vendor', 'Unknown'),
                  'domain': record.domain, 'workflow': record.report_status or 'pending'}
        if any(filters.get(field) and values[field] not in filters[field] for field in values):
            continue
        date = record.report_metadata.get('report_date') or record.report_date
        if filters.get('date_start') or filters.get('date_end'):
            if not date:
                continue
            if filters.get('date_start') and date < str(filters['date_start']):
                continue
            if filters.get('date_end') and date > str(filters['date_end']):
                continue
        output.append(record)
    return output


def finding_rows(records: list[Record], filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    rows = []
    for record in records:
        for finding in record.findings:
            row = {'finding_id': finding.finding_id, 'record_id': record.record_id,
                'report_id': report_key(record), 'vendor': record.report_metadata.get('vendor', 'Unknown'),
                'domain': record.domain, 'date': record.report_metadata.get('report_date') or record.report_date,
                'defect': finding.category or 'Uncategorized: ' + finding.defect.text.casefold(),
                'evidence': finding.defect.text, 'assertion': finding.defect.assertion,
                'priority': finding.priority, 'reasons': '; '.join(finding.priority_reasons),
                'workflow': record.report_status or 'pending', 'ambiguous': finding.ambiguous,
                'component': [e.text.casefold() for e in finding.links.get('COMPONENT', [])] or ['Unknown'],
                'material': [e.text.casefold() for e in finding.links.get('MATERIAL', [])] or ['Unknown'],
                'severity': [e.text.casefold() for e in finding.links.get('REPORTED_SEVERITY', [])] or ['Unknown'],
                'recurrence': len(finding.recurrence_previous)}
            if any(filters.get(field) and not set(row[field]) & set(filters[field]) for field in ('component', 'material')):
                continue
            if any(filters.get(field) and row[field] not in filters[field] for field in ('defect', 'assertion')):
                continue
            rows.append(row)
    return rows


def overview(records: list[Record], rows: list[dict]) -> dict:
    active = [row for row in rows if row['assertion'] == 'present']
    return {'reports': len({report_key(r) for r in records}), 'narratives': len(records),
            'active_defects': len(active), 'affected_reports': len({row['report_id'] for row in active}),
            'pending_reports': len({report_key(r) for r in records if r.report_status != 'reviewed'})}


def vendor_rates(records: list[Record], rows: list[dict]) -> list[dict]:
    vendors = sorted({r.report_metadata.get('vendor', 'Unknown') for r in records})
    output = []
    for vendor in vendors:
        inspected = {report_key(r) for r in records if r.report_metadata.get('vendor', 'Unknown') == vendor}
        affected = {row['report_id'] for row in rows if row['vendor'] == vendor and row['assertion'] == 'present'}
        count = len(inspected)
        output.append({'vendor': vendor, 'inspected_reports': count, 'affected_reports': len(affected),
                       'affected_report_rate': 100 * len(affected) / count if count else 0})
    return output


def monthly_trends(records: list[Record], rows: list[dict]) -> tuple[list[dict], int]:
    buckets = {}
    undated = set()
    for record in records:
        date = record.report_metadata.get('report_date') or record.report_date
        if not date:
            undated.add(report_key(record))
            continue
        month = date[:7]
        bucket = buckets.setdefault(month, {'inspected': set(), 'affected': set(), 'active': 0})
        bucket['inspected'].add(report_key(record))
    for row in rows:
        if row['date'] and row['assertion'] == 'present':
            bucket = buckets[row['date'][:7]]
            bucket['affected'].add(row['report_id'])
            bucket['active'] += 1
    return [{'month': month, 'inspected_reports': len(b['inspected']),
             'affected_reports': len(b['affected']), 'active_defects': b['active'],
             'affected_report_rate': 100 * len(b['affected']) / len(b['inspected'])}
            for month, b in sorted(buckets.items())], len(undated)


def heatmap_cells(rows: list[dict], field: str) -> list[dict]:
    cells = {}
    for row in rows:
        values = row[field] if isinstance(row[field], list) else [row[field]]
        for value in values:
            cells.setdefault((value, row['defect']), set()).add(row['finding_id'])
    return [{'group': group, 'defect': defect, 'count': len(ids)} for (group, defect), ids in sorted(cells.items())]


def cooccurrence_cells(records: list[Record], field: str) -> list[dict]:
    groups = {}
    for record in records:
        values, defects = groups.setdefault(report_key(record), (set(), set()))
        values.update(e.text.casefold() for e in record.entities if e.label == field)
        defects.update(f.category or 'Uncategorized: ' + f.defect.text.casefold() for f in record.findings)
    counts = Counter((value, defect) for values, defects in groups.values() for value in values for defect in defects)
    return [{'group': group, 'defect': defect, 'count': count} for (group, defect), count in sorted(counts.items())]


def export_scope(records: list[Record], rows: list[dict]) -> list[Record]:
    """Keep denominator reports, but only selected findings and their entity evidence."""
    selected = {row['finding_id'] for row in rows}
    output = []
    for record in records:
        payload = record.model_dump()
        findings = [f for f in record.findings if f.finding_id in selected]
        keys = {(e.label, e.evidence_start, e.evidence_end) for f in findings
                for e in [f.defect, *(e for values in f.links.values() for e in values)]}
        retain_all = len(findings) == len(record.findings)
        payload.update(findings=[f.model_dump() for f in findings],
            entities=[e.model_dump() for e in record.entities if retain_all or (e.label, e.evidence_start, e.evidence_end) in keys],
            relations=[r for r in record.relations if r.get('finding_id') in selected])
        output.append(Record.model_validate(payload))
    return output


def review_queue(records: list[Record], rows: list[dict]) -> list[dict]:
    from datetime import UTC, datetime
    output = []
    lookup = {r.record_id: r for r in records}
    for row in rows:
        if row['workflow'] != 'reviewed':
            output.append(dict(row))
    for record in records:
        if record.report_status == 'reviewed':
            continue
        for candidate in record.review_candidates:
            output.append({'record_id': record.record_id, 'report_id': report_key(record),
                'vendor': record.report_metadata.get('vendor', 'Unknown'), 'evidence': candidate.text,
                'priority': 'normal' if record.review_priority is not None else 'disabled',
                'reasons': candidate.reason, 'workflow': record.report_status or 'pending'})
        if record.quality_flags and not record.findings and not record.review_candidates:
            output.append({'record_id': record.record_id, 'report_id': report_key(record),
                'vendor': record.report_metadata.get('vendor', 'Unknown'), 'evidence': 'Extraction quality review',
                'priority': 'normal' if record.review_priority is not None else 'disabled',
                'reasons': '; '.join(record.quality_flags), 'workflow': record.report_status or 'pending'})
    for row in output:
        created = lookup[row['record_id']].document_metadata.get('created_at')
        try:
            row['age_days'] = max(0, (datetime.now(UTC) - datetime.fromisoformat(created)).days) if created else 0
        except ValueError:
            row['age_days'] = 0
    order = {'high': 0, 'normal': 1, 'low': 2, 'disabled': 3}
    return sorted(output, key=lambda row: (order[row['priority']], -row['age_days']))
