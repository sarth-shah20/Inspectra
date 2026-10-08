import pytest

from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract
from inspection_nlp.findings import edit_relationships, relationship_rows
from inspection_nlp.reviews import review_payload


def report(text):
    return extract(parse_document(text.encode(), 'new.txt', domain='pipeline')[0])


def test_separate_clauses_and_ambiguous_evidence():
    r = report('Steel valve cracked at 3 mm; copper pipe leaking.')
    assert len(r.findings) == 2
    assert r.findings[0].links['MATERIAL'][0].text == 'Steel'
    assert r.findings[1].links['MATERIAL'][0].text == 'copper'
    ambiguous = report('Valve and pipe cracked and leaking.')
    assert all(f.ambiguous and not f.links for f in ambiguous.findings)


def test_reviewed_relationships_and_offsets():
    r = report('Critical valve cracked at 3 mm.')
    assert r.findings[0].links['REPORTED_SEVERITY'][0].text == 'Critical'
    edited = edit_relationships(r, [])
    assert not edited.findings[0].links
    with pytest.raises(ValueError, match='existing evidence'):
        edit_relationships(r, [{**relationship_rows(r)[0], 'start': 999}])
    payload = review_payload(r, [e.model_dump() for e in r.entities], 'Unlinked', [])
    assert not payload['corrected_findings'][0]['links']


def test_assertions_and_uncategorized():
    for text, status in [('No crack observed.', 'negated'), ('Previous crack documented.', 'historical'),
                         ('Crack was repaired.', 'resolved'), ('Failed to find a crack.', 'negated')]:
        assert report(text).findings[0].defect.assertion == status
