"""Conservative evidence relationships and versioned generic defect categories."""

from importlib.resources import files

import yaml

from .contextual import clauses
from .schemas import Finding, Record

LINK_LABELS = {'COMPONENT', 'MATERIAL', 'MEASUREMENT', 'REPORTED_SEVERITY',
               'CAUSE', 'CORRECTIVE_ACTION', 'INSPECTION_METHOD', 'LOCATION'}


def defect_category(text: str) -> str | None:
    config = yaml.safe_load(files('inspection_nlp').joinpath('configs/defect_categories.yaml').read_text())
    for category, terms in config['categories'].items():
        if text.casefold() in terms:
            return category
    return None


def build_findings(record: Record) -> list[Finding]:
    findings = []
    bounds = list(clauses(record.display_text))
    for defect in (e for e in record.entities if e.label == 'DEFECT'):
        start, end = next(((a, b) for a, b in bounds if a <= defect.evidence_start < b),
                          (defect.evidence_start, defect.evidence_end))
        local = [e for e in record.entities if start <= e.evidence_start and e.evidence_end <= end]
        defects = [e for e in local if e.label == 'DEFECT']
        links, ambiguous = {}, len(defects) > 1
        for label in sorted(LINK_LABELS):
            evidence = [e for e in local if e.label == label]
            if len(defects) == 1 and len(evidence) == 1:
                links[label] = evidence
            elif evidence:
                ambiguous = True
        findings.append(Finding(finding_id=f'{record.record_id}:defect:{defect.evidence_start}',
            defect=defect, category=defect_category(defect.text), links=links, ambiguous=ambiguous))
    return findings


def with_findings(record: Record) -> Record:
    payload = record.model_dump()
    payload['findings'] = [f.model_dump() for f in build_findings(record)]
    payload['relations'] = [
        {'finding_id': f['finding_id'], 'label': label, 'evidence_start': e['evidence_start'],
         'evidence_end': e['evidence_end']}
        for f in payload['findings'] for label, evidence in f['links'].items() for e in evidence]
    return Record.model_validate(payload)


def relationship_rows(record: Record) -> list[dict]:
    return [{'finding_id': f.finding_id, 'label': label, 'start': e.evidence_start,
             'end': e.evidence_end, 'text': e.text}
            for f in record.findings for label, evidence in f.links.items() for e in evidence]


def edit_relationships(record: Record, rows: list[dict]) -> Record:
    """Accept only explicit references to current record evidence."""
    payload = record.model_dump()
    lookup = {f['finding_id']: f for f in payload['findings']}
    for f in lookup.values():
        f['links'] = {}
    for row in rows:
        if row['finding_id'] not in lookup:
            raise ValueError('Unknown finding reference')
        label, start, end = row['label'], int(row['start']), int(row['end'])
        evidence = next((e for e in record.entities if e.label == label and e.evidence_start == start and e.evidence_end == end), None)
        if label not in LINK_LABELS or evidence is None:
            raise ValueError('Relationship must reference existing evidence')
        linked = lookup[row['finding_id']]['links'].setdefault(label, [])
        if evidence.model_dump() not in linked:
            linked.append(evidence.model_dump())
    reviewed = Record.model_validate(payload)
    payload['relations'] = relationship_rows(reviewed)
    return Record.model_validate(payload)
