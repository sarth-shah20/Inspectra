from inspection_nlp import analytics
from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract


def fixtures():
    return [extract(parse_document(text, f'{i}.txt', domain='textile', report_metadata=metadata)[0])
        for i, (text, metadata) in enumerate([
            (b'Ceramic spindle cracked.', {'vendor': 'Vendor A', 'report_date': '2026-01-01'}),
            (b'No crack observed.', {'vendor': 'Vendor A', 'report_date': '2026-01-02'}),
            (b'Steel spindle leaking.', {'vendor': 'Vendor B'}),
        ])]


def test_rates_and_filter_denominators():
    records = fixtures()
    rows = analytics.finding_rows(records, {'defect': ['crack'], 'assertion': ['present']})
    rates = {r['vendor']: r for r in analytics.vendor_rates(records, rows)}
    assert rates['vendor a']['affected_report_rate'] == 50
    assert rates['vendor a']['inspected_reports'] == 2
    assert rates['vendor b']['affected_reports'] == 0
    scope = analytics.scope_records(records, {'vendor': ['vendor a']})
    assert len(scope) == 2
    assert analytics.overview(scope, rows)['affected_reports'] == 1
    trends, missing = analytics.monthly_trends(records, rows)
    assert missing == 1 and trends[0]['affected_report_rate'] == 50


def test_link_heatmaps_and_export_selection():
    records = fixtures()
    rows = analytics.finding_rows(records, {'material': ['ceramic']})
    assert len(rows) == 1
    cells = analytics.heatmap_cells(rows, 'material')
    assert cells == [{'group': 'ceramic', 'defect': 'crack', 'count': 1}]
    exported = analytics.export_scope(records, rows)
    assert sum(len(r.findings) for r in exported) == 1
    assert len(exported) == 3


def test_pages_render(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    from inspection_nlp.storage import Library
    monkeypatch.setenv('INSPECTRA_DB', str(tmp_path / 'library.sqlite3'))
    Library(tmp_path / 'library.sqlite3').save_run(fixtures(), {})
    for page in ['Overview', 'Defect analysis', 'Vendor comparison', 'Trends', 'Review queue', 'Model quality']:
        app = AppTest.from_string(f'from inspection_nlp.dashboard import main\nmain(page={page!r})').run()
        assert not app.exception, page
