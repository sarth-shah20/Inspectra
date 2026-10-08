"""Local SQLite report library; automated runs and review revisions are immutable."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from contextlib import contextmanager
from pathlib import Path

from .findings import with_findings
from .schemas import Record

SCHEMA_VERSION = 1


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Library:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError('Database is newer than this application; restore compatible software')
            if version == 0:
                db.executescript('''
                    CREATE TABLE reports (report_id TEXT PRIMARY KEY, source_hash TEXT NOT NULL);
                    CREATE TABLE runs (run_id TEXT PRIMARY KEY, settings TEXT NOT NULL, created_at TEXT NOT NULL);
                    CREATE TABLE records (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs,
                        record_id TEXT NOT NULL, report_id TEXT NOT NULL REFERENCES reports,
                        payload TEXT NOT NULL, UNIQUE(run_id, record_id));
                    CREATE TABLE revisions (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL,
                        record_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                        FOREIGN KEY(run_id, record_id) REFERENCES records(run_id, record_id));
                    CREATE TABLE imports (import_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                        revision_id INTEGER REFERENCES revisions, status TEXT NOT NULL);
                    CREATE INDEX revisions_lookup ON revisions(run_id, record_id, id);
                    PRAGMA user_version=1;
                ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_run(self, records: list[Record], settings: dict) -> list[Record]:
        output = []
        with self.connect() as db:
            for record in records:
                payload = record.model_dump()
                payload['document_metadata'].pop('run_id', None)
                run_id = digest({'record': payload, 'settings': settings})
                payload['report_id'] = record.report_id or record.source_event_id
                payload['document_metadata']['run_id'] = run_id
                db.execute('INSERT OR IGNORE INTO reports VALUES (?, ?)',
                           (payload['report_id'], record.source_sha256))
                db.execute('INSERT OR IGNORE INTO runs VALUES (?, ?, ?)',
                           (run_id, json.dumps(settings, sort_keys=True), now()))
                db.execute('INSERT OR IGNORE INTO records(run_id,record_id,report_id,payload) VALUES (?,?,?,?)',
                           (run_id, record.record_id, payload['report_id'], json.dumps(payload)))
                output.append(Record.model_validate(payload))
        return output

    def records(self, reviewed: bool = True) -> list[Record]:
        with self.connect() as db:
            rows = db.execute('''SELECT * FROM records WHERE id IN
                (SELECT MAX(id) FROM records GROUP BY record_id) ORDER BY id DESC''').fetchall()
            result = []
            for row in rows:
                revision = db.execute('SELECT * FROM revisions WHERE run_id=? AND record_id=? ORDER BY id DESC LIMIT 1',
                    (row['run_id'], row['record_id'])).fetchone() if reviewed else None
                payload = json.loads(revision['payload'] if revision else row['payload'])
                if revision:
                    payload['document_metadata'].update(review_version=str(revision['id']), reviewed_at=revision['created_at'])
                payload['document_metadata']['created_at'] = db.execute('SELECT created_at FROM runs WHERE run_id=?', (row['run_id'],)).fetchone()[0]
                result.append(Record.model_validate(payload))
            return result

    def save_review(self, record: Record, correction: dict, workflow: str = 'reviewed') -> Record:
        if workflow not in {'pending', 'in_progress', 'reviewed'}:
            raise ValueError('Unknown workflow status')
        run_id = record.document_metadata.get('run_id')
        payload = record.model_dump()
        payload.update(entities=correction['corrected_entities'], findings=[], relations=[], label_origin='human', report_status=workflow)
        reviewed = with_findings(Record.model_validate(payload))
        if 'corrected_findings' in correction:
            payload = reviewed.model_dump()
            payload['findings'] = correction['corrected_findings']
            payload['relations'] = [{'finding_id': f['finding_id'], 'label': label,
                'evidence_start': e['evidence_start'], 'evidence_end': e['evidence_end']}
                for f in payload['findings'] for label, values in f['links'].items() for e in values]
            reviewed = Record.model_validate(payload)
        payload = reviewed.model_dump()
        defects = [e for e in reviewed.entities if e.label == 'DEFECT']
        statuses = {e.assertion for e in defects}
        payload.update(mapping_status='review_required' if workflow != 'reviewed' and (defects or reviewed.review_candidates) else 'mapped' if workflow == 'reviewed' else 'unmapped',
            assertion_status=next(iter(statuses)) if len(statuses) == 1 else 'unknown',
            reported_severity='; '.join(dict.fromkeys(e.text for e in reviewed.entities if e.label == 'REPORTED_SEVERITY' and e.assertion == 'present')) or None)
        payload['document_metadata']['review_note'] = correction.get('note', '')
        timestamp = now()
        with self.connect() as db:
            cursor = db.execute('INSERT INTO revisions(run_id,record_id,payload,created_at) VALUES (?,?,?,?)',
                                (run_id, record.record_id, json.dumps(payload), timestamp))
            payload['document_metadata'].update(review_version=str(cursor.lastrowid), reviewed_at=timestamp)
        from .priority import prioritize
        return prioritize(Record.model_validate(payload))

    def history(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,record_id,created_at FROM revisions ORDER BY id DESC')]

    def import_legacy(self, path: Path) -> dict[str, int]:
        from .reviews import review_history
        counts = {'matched': 0, 'unmatched': 0, 'already_imported': 0}
        for correction in reversed(review_history(path)):
            key = digest(correction)
            with self.connect() as db:
                if db.execute('SELECT 1 FROM imports WHERE import_id=?', (key,)).fetchone():
                    counts['already_imported'] += 1
                    continue
                rows = db.execute('SELECT * FROM records WHERE id IN (SELECT MAX(id) FROM records GROUP BY record_id)').fetchall()
                matching = [row for row in rows if (json.loads(row['payload'])['record_id'] == correction['record_id']
                    or correction['record_id'] == ':'.join([json.loads(row['payload'])['record_id'].split(':')[0], json.loads(row['payload'])['source_sha256'][:16], json.loads(row['payload'])['source_record_id']]))
                    and json.loads(row['payload'])['display_text'] == correction.get('display_text')]
                revision_id = None
                if len(matching) == 1:
                    original = Record.model_validate(json.loads(matching[0]['payload']))
                    payload = original.model_dump()
                    payload.update(entities=correction['corrected_entities'], findings=[], relations=[], label_origin='human', report_status='reviewed', mapping_status='mapped')
                    reviewed = with_findings(Record.model_validate(payload))
                    cursor = db.execute('INSERT INTO revisions(run_id,record_id,payload,created_at) VALUES (?,?,?,?)',
                        (original.document_metadata['run_id'], original.record_id, reviewed.model_dump_json(), correction['reviewed_at']))
                    revision_id = cursor.lastrowid
                status = 'matched' if revision_id else 'unmatched'
                db.execute('INSERT INTO imports VALUES (?,?,?,?)', (key, json.dumps(correction), revision_id, status))
                counts[status] += 1
        return counts

    def backup(self, destination: Path):
        destination = Path(destination)
        if destination.exists() or destination.resolve() == self.path.resolve():
            raise ValueError('Backup destination must be a new file')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
