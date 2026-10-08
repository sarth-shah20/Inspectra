import sqlite3

import pytest

from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract
from inspection_nlp.reviews import append_review, review_payload
from inspection_nlp.storage import Library


def test_persistence_duplicate_and_revisions(tmp_path):
    path = tmp_path / 'library.sqlite3'
    lib = Library(path)
    r = extract(parse_document(b'Steel spindle cracked.', 'new.txt')[0])
    saved = lib.save_run([r], {'model': 'v1'})[0]
    lib.save_run([r], {'model': 'v1'})
    assert len(lib.records()) == 1
    payload = review_payload(saved, [], 'No supported defect', [])
    lib.save_review(saved, payload)
    restarted = Library(path)
    assert restarted.records()[0].entities == []
    assert restarted.records(False)[0].entities
    assert restarted.records()[0].mapping_status == 'mapped'
    newer = lib.save_run([r], {'model': 'v2'})[0]
    assert newer.document_metadata['run_id'] != saved.document_metadata['run_id']
    assert lib.records()[0].label_origin != 'human'
    backup = tmp_path / 'backup.sqlite3'
    lib.backup(backup)
    assert Library(backup).records()[0].record_id == r.record_id


def test_legacy_import_idempotent_and_unmatched(tmp_path):
    lib = Library(tmp_path / 'library.sqlite3')
    r = lib.save_run([extract(parse_document(b'Valve cracked.', 'new.txt')[0])], {})[0]
    path = tmp_path / 'old.jsonl'
    payload = review_payload(r, [e.model_dump() for e in r.entities], 'Confirmed')
    append_review(path, payload)
    append_review(path, {**payload, 'record_id': 'missing'})
    assert lib.import_legacy(path) == {'matched': 1, 'unmatched': 1, 'already_imported': 0}
    assert lib.import_legacy(path)['already_imported'] == 2
    assert len(lib.history()) == 1


def test_failed_write_rolls_back_and_version_gate(tmp_path):
    lib = Library(tmp_path / 'library.sqlite3')
    r = extract(parse_document(b'Valve cracked.', 'new.txt')[0])
    with pytest.raises(sqlite3.IntegrityError):
        lib.save_review(r, review_payload(r, [], 'Not persisted', []))
    assert not lib.history()
    with lib.connect() as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='newer'):
        Library(lib.path)
