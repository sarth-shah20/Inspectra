import pytest

from inspection_nlp.documents import parse_batch, parse_document
from inspection_nlp.metadata import load_profiles, save_profile, vendor_key


def test_unseen_vendor_and_mapping():
    data = b'Notes,Supplier,When,Code,Target\nSteel spindle cracked., Zorb GmbH ,09/10/2026,A1,FAILED\n'
    r = parse_document(data, 'unknown.csv', domain='textile', text_column='Notes',
        metadata_columns={'vendor': 'Supplier', 'report_date': 'When', 'asset_id': 'Code'},
        date_format='%d/%m/%Y')[0]
    assert r.domain == 'textile'
    assert r.report_metadata == {'vendor': 'zorb gmbh', 'report_date': '2026-10-09', 'asset_id': 'A1'}
    assert 'FAILED' not in r.model_dump_json()
    assert r.metadata_provenance['vendor'] == 'column:Supplier'
    assert vendor_key(' ZORB GmbH ', {'zorb gmbh': 'Zorb'}) == 'zorb'
    with pytest.raises(ValueError, match='ambiguous'):
        parse_document(data, 'unknown.csv', text_column='Notes', metadata_columns={'report_date': 'When'})


def test_evidence_boundaries_and_offsets():
    r = parse_document(b'Steel\n\nspindle\tcracked.', 'note.txt')[0]
    assert '\n\n' in r.display_text
    assert r.clean_text == 'Steel spindle cracked.'
    start = r.clean_text.index('cracked')
    assert r.display_text[r.clean_to_display[start]:r.clean_to_display[start+7]] == 'cracked'


def test_batch_failure_isolated_and_profiles(tmp_path):
    rows, errors = parse_batch([('empty.txt', b''), ('new.txt', b'Ceramic spindle cracked.')])
    assert len(rows) == len(errors) == 1
    assert errors[0]['file'] == 'empty.txt'
    path = tmp_path / 'profiles.json'
    save_profile(path, 'arbitrary', {'text_column': 'Notes'})
    assert load_profiles(path)['arbitrary']['text_column'] == 'Notes'


def test_pdf_report_identity():
    import pymupdf
    with pymupdf.open() as doc:
        for _ in range(2):
            doc.new_page().insert_text((72, 72), 'Spindle cracked.')
        records = parse_document(doc.tobytes(), 'two.pdf')
    assert len(records) == 2
    assert len({r.report_id for r in records}) == 1
