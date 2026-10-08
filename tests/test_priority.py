from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract
from inspection_nlp.priority import prioritize, with_recurrence


def record(text, **metadata):
    return extract(parse_document(text.encode(), text+'.txt', report_metadata=metadata)[0])


def test_explicit_urgency_and_resolved():
    high = record('Critical spindle cracked; valve inspected.')
    assert high.findings[0].priority == 'high'
    assert high.findings[0].priority_reasons
    assert record('Spindle cracked; critical valve inspected.').findings[0].priority == 'normal'
    assert record('No critical crack found.').findings[0].priority == 'low'
    assert record('Critical crack was repaired.').findings[0].priority == 'low'
    assert prioritize(high, False).review_priority is None
    assert prioritize(high, False).findings[0].priority == 'disabled'
    assert record('The zorbulator is cracked.').findings[0].priority == 'normal'


def test_recurrence_requires_identity_and_chronology():
    first = record('Spindle cracked.', vendor='Arbitrary Ltd', asset_id='A', report_date='2026-01-01')
    later = record('Spindle cracked again.', vendor='arbitrary ltd', asset_id='A', report_date='2026-02-01')
    missing = record('Spindle cracked elsewhere.', vendor='arbitrary ltd', report_date='2026-03-01')
    records = with_recurrence([first, later, missing])
    assert not records[0].findings[0].recurrence_previous
    assert records[1].findings[0].recurrence_previous == [first.findings[0].finding_id]
    assert records[2].document_metadata['recurrence_status'] == 'insufficient_linkage'
