"""Purpose-specific local Streamlit dashboard over shared analytics services."""

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import joblib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import analytics
from .classification import predict
from .contextual import english_model
from .documents import parse_batch, table_headers
from .export import export_csv, export_json, export_html, highlight
from .extraction import extract
from .findings import relationship_rows
from .hybrid import extract_hybrid
from .metadata import FIELDS, load_profiles, save_profile
from .priority import prioritize, with_recurrence
from .reviews import review_payload
from .storage import Library

ROOT = Path(__file__).resolve().parents[2]
PAGES = ['Overview', 'Report explorer', 'Defect analysis', 'Vendor comparison', 'Trends', 'Review queue', 'Model quality']


def table(rows):
    st.dataframe(rows, hide_index=True, width='stretch')


def evidence_table(records, rows, selection=None):
    if selection:
        field, values = selection
        rows = [r for r in rows if (set(r[field]) & set(values) if isinstance(r[field], list) else r[field] in values)]
    st.caption(f'{len(rows)} matching defect findings. Unknown means evidence was not linked or metadata was not supplied.')
    table([{**r, 'component': ', '.join(r['component']), 'material': ', '.join(r['material']),
            'severity': ', '.join(r['severity'])} for r in rows])
    if rows:
        choices = list(dict.fromkeys(r['record_id'] for r in rows))
        selected = st.selectbox('Inspect supporting narrative', choices, key='evidence_drill')
        record = next(r for r in records if r.record_id == selected)
        st.markdown(f'<div style="white-space:pre-wrap">{highlight(record)}</div>', unsafe_allow_html=True)
        st.caption(f'{record.source_document} · {record.document_metadata.get("page", "document")}')


def bar(rows, field, value, title, key):
    if not rows:
        st.info('No data for this view.')
        return []
    figure = go.Figure(go.Bar(x=[r[field] for r in rows], y=[r[value] for r in rows],
        customdata=[r[field] for r in rows], marker_color='#168a8a'))
    figure.update_layout(title=title, xaxis_title=field.replace('_', ' ').title(), yaxis_title=value.replace('_', ' ').title())
    event = st.plotly_chart(figure, key=key, on_select='rerun', selection_mode='points', width='stretch')
    return [point['customdata'] for point in event.selection.points if 'customdata' in point]


def heatmap(cells, title, key):
    if not cells:
        st.info('No evidence for this heatmap.')
        return []
    groups, defects = sorted({r['group'] for r in cells}), sorted({r['defect'] for r in cells})
    # Square markers permit Streamlit point selection; color/size encode cell counts.
    figure = go.Figure(go.Scatter(x=[r['defect'] for r in cells], y=[r['group'] for r in cells],
        mode='markers', marker={'symbol': 'square', 'size': 28, 'color': [r['count'] for r in cells],
        'colorscale': 'Teal', 'showscale': True, 'colorbar': {'title': 'Findings'}},
        customdata=[[r['group'], r['defect'], r['count']] for r in cells],
        hovertemplate='%{y} × %{x}<br>Count: %{customdata[2]}<extra></extra>'))
    figure.update_layout(title=title, xaxis={'categoryorder': 'array', 'categoryarray': defects},
                         yaxis={'categoryorder': 'array', 'categoryarray': groups})
    event = st.plotly_chart(figure, key=key, on_select='rerun', selection_mode='points', width='stretch')
    return [point['customdata'][:2] for point in event.selection.points if 'customdata' in point]


def filter_sidebar(records):
    all_rows = analytics.finding_rows(records)
    filters = {}
    st.sidebar.subheader('Shared report filters')
    for field, label, values in [
        ('vendor', 'Vendor', [r.report_metadata.get('vendor', 'Unknown') for r in records]),
        ('domain', 'Industry', [r.domain for r in records]),
        ('workflow', 'Review status', [r.report_status or 'pending' for r in records]),
        ('material', 'Material', [v for row in all_rows for v in row['material']]),
        ('component', 'Component', [v for row in all_rows for v in row['component']]),
        ('defect', 'Defect', [row['defect'] for row in all_rows]),
        ('assertion', 'Assertion', [row['assertion'] for row in all_rows]),
    ]:
        filters[field] = st.sidebar.multiselect(label, sorted(set(values)), key=f'filter_{field}')
    if st.sidebar.checkbox('Filter report dates'):
        filters['date_start'] = st.sidebar.date_input('From', key='date_from').isoformat()
        filters['date_end'] = st.sidebar.date_input('To', key='date_to').isoformat()
        if filters['date_start'] > filters['date_end']:
            st.sidebar.error('From date must not follow To date.')
    scope = analytics.scope_records(records, filters)
    return scope, analytics.finding_rows(scope, filters), filters


def report_explorer(library, records, rows, settings, filters):
    st.subheader('Add inspection reports')
    uploads = st.file_uploader('Upload reports', type=['pdf', 'docx', 'txt', 'csv', 'tsv', 'xlsx'], accept_multiple_files=True)
    paste = st.text_area('Or paste a narrative', height=130)
    text_column = st.text_input('Narrative column', help='Use a column mapping below for tables.')
    tabular = st.checkbox('My TXT file is tabular')
    encoding = st.selectbox('Text encoding', ['utf-8-sig', 'cp1252'])
    date_format = st.selectbox('Date format', ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'])
    metadata, columns = {}, {}
    local = library.path.parent
    with st.expander('Report metadata and reusable mappings'):
        profiles = load_profiles(local / 'mappings.json')
        name = st.selectbox('Saved mapping', ['None', *profiles])
        profile = profiles.get(name, {})
        headers = []
        if uploads and (Path(uploads[0].name).suffix.lower() in {'.csv', '.tsv', '.xlsx'} or tabular):
            try:
                headers = table_headers(uploads[0].getvalue(), uploads[0].name, encoding)
            except (ValueError, UnicodeError, RuntimeError) as exc:
                st.error(str(exc))
        if headers:
            default = profile.get('text_column')
            text_column = st.selectbox('Narrative column mapping', headers, index=headers.index(default) if default in headers else 0, key=f'narrative_map_{name}')
        for field in FIELDS:
            metadata[field] = st.text_input(field.replace('_', ' ').title(), key=f'metadata_{field}')
            if headers:
                options = ['Not mapped', *headers]
                default = profile.get('metadata_columns', {}).get(field, 'Not mapped')
                mapped = st.selectbox(f'Column for {field}', options, index=options.index(default) if default in options else 0, key=f'map_{field}_{name}')
                if mapped != 'Not mapped':
                    columns[field] = mapped
        aliases_text = st.text_area('Explicit vendor aliases (JSON)', value='{}', help='Example: {"Acme Ltd.": "Acme"}')
        profile_name = st.text_input('Mapping profile name')
        if st.button('Save mapping profile'):
            try:
                save_profile(local / 'mappings.json', profile_name, {'text_column': text_column, 'metadata_columns': columns})
                st.success('Mapping saved')
            except ValueError as exc:
                st.error(str(exc))
    signature = hashlib.sha256(repr(([(u.name, u.getvalue()) for u in uploads], paste, text_column, tabular,
        encoding, date_format, metadata, columns, aliases_text, {k: v for k, v in settings.items() if k != "priority"})).encode()).hexdigest()
    if st.session_state.get('analysis_signature') != signature:
        st.session_state.pop('results', None)
        st.session_state.pop('classification', None)
    if st.button('Analyze findings', type='primary'):
        if not uploads and not paste.strip():
            st.warning('Add a report or paste a narrative before analyzing.')
        else:
            try:
                aliases = json.loads(aliases_text)
                if not isinstance(aliases, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()):
                    raise ValueError('Vendor aliases must be a JSON object of names')
                files = [(u.name, u.getvalue()) for u in uploads]
                if paste.strip():
                    files.append(('pasted.txt', paste.encode()))
                parsed, errors = parse_batch(files, domain=settings['domain'], text_column=text_column or None,
                    tabular_txt=tabular, encoding=encoding if uploads else 'utf-8-sig', metadata_columns=columns,
                    report_metadata=metadata, date_format=date_format, vendor_aliases=aliases)
                results = []
                for r in parsed:
                    try:
                        result = extract_hybrid(r, ROOT / 'models/silver-ner-v1', threshold=0.5,
                            pack_paths=settings['packs']) if settings['hybrid'] else extract(r, pack_paths=settings['packs'])
                        results.append(result)
                    except (ValueError, OSError, RuntimeError) as exc:
                        errors.append({'file': r.source_document, 'error': str(exc)})
                for error in errors:
                    st.error(f"{error['file']}: {error['error']}")
                st.session_state['results'] = library.save_run(results, {k: v for k, v in settings.items() if k != "priority"})
                st.session_state['analysis_signature'] = signature
                if results:
                    st.success(f'Saved {len(results)} narratives to the report library.')
                    records = with_recurrence([prioritize(r, settings['priority']) for r in library.records()])
                    records = analytics.scope_records(records, filters)
                    rows = analytics.finding_rows(records, filters)
            except (ValueError, UnicodeError, OSError) as exc:
                st.error(str(exc))
    st.subheader('Report library')
    if not records:
        st.info('Upload reports to begin. Vendor and industry names are unrestricted.')
        return
    record = select_record(records)
    show_record(record, library, settings)
    downloads(analytics.export_scope(records, rows))


def select_record(records):
    choices = {f'{r.source_document} · {r.report_metadata.get("vendor", "Unknown")} · {r.document_metadata.get("page", r.source_row)} · {r.record_id[-8:]}': r for r in records}
    pending = st.session_state.pop('open_record', None)
    labels = list(choices)
    default = next((i for i, label in enumerate(labels) if choices[label].record_id == pending), 0)
    key = 'record_select_' + hashlib.sha256(''.join(r.record_id for r in records).encode()).hexdigest()[:12]
    if pending:
        st.session_state[key] = labels[default]
    label = st.selectbox('Narrative', labels, index=default, key=key)
    return choices[label]


def show_record(record, library, settings):
    st.subheader(f'Findings · {"Reviewed" if record.report_status == "reviewed" else "Needs review" if record.mapping_status == "review_required" else "No supported defect extracted"}')
    st.caption(f"Extraction: {record.document_metadata.get('extraction_mode', 'unknown')} · Industry: {record.domain} · Scores are heuristic, not calibrated probabilities.")
    st.markdown(f'<div style="white-space:pre-wrap">{highlight(record)}</div>', unsafe_allow_html=True)
    st.caption('Highlighted spans show extracted evidence; their labels and assertions appear below.')
    table([e.model_dump() for e in record.entities])
    table([{'Defect': f.defect.text, 'Category': f.category or 'Uncategorized', 'Assertion': f.defect.assertion,
            'Priority': f.priority, 'Reasons': '; '.join(f.priority_reasons), 'Ambiguous links': f.ambiguous,
            'Earlier findings': len(f.recurrence_previous)} for f in record.findings])
    if record.quality_flags:
        st.warning('Extraction quality: ' + '; '.join(record.quality_flags))
    if record.review_candidates:
        st.info('Unsupported inspection/action clauses require review; they are not confirmed defects.')
        table([c.model_dump() for c in record.review_candidates])
    token = record.document_metadata.get('run_id', record.record_id) + record.document_metadata.get('review_version', '')
    with st.expander('Review and correct evidence', expanded=False):
        columns = list(record.entities[0].model_dump()) if record.entities else ['label', 'text', 'evidence_start', 'evidence_end', 'assertion', 'confidence', 'extraction_method']
        frame = pd.DataFrame([e.model_dump() for e in record.entities], columns=columns)
        labels = list(__import__('inspection_nlp.schemas', fromlist=['Entity']).Entity.model_fields['label'].annotation.__args__)
        edited = st.data_editor(frame, num_rows='dynamic', hide_index=True, key=f'entities_{token}',
            disabled=['text', 'confidence', 'extraction_method'], column_config={
                'label': st.column_config.SelectboxColumn(options=labels, required=True),
                'assertion': st.column_config.SelectboxColumn(options=['present', 'negated', 'possible', 'historical', 'resolved'], required=True),
                'evidence_start': st.column_config.NumberColumn(min_value=0, step=1, required=True),
                'evidence_end': st.column_config.NumberColumn(min_value=1, step=1, required=True)})
        st.caption('Offsets reference the displayed text. Add missed spans by entering their label, assertion, and offsets.')
        links = st.data_editor(pd.DataFrame(relationship_rows(record), columns=['finding_id', 'label', 'start', 'end', 'text']),
            num_rows='dynamic', disabled=['text'], key=f'links_{token}', hide_index=True)
        keep_links = st.checkbox('Use edited relationships', value=True, key=f'use_links_{token}', help='Clear to rebuild conservative links after adding or changing defect spans.')
        workflow = st.selectbox('Review workflow', ['reviewed', 'in_progress', 'pending'], key=f'workflow_{token}')
        note = st.text_area('Review note', key=f'note_{token}')
        if st.button('Save correction', key=f'save_{token}'):
            try:
                correction = review_payload(record, edited.to_dict('records'), note, links.to_dict('records') if keep_links else None)
                corrected = library.save_review(record, correction, workflow)
                for i, current in enumerate(st.session_state.get('results', [])):
                    if current.record_id == corrected.record_id:
                        st.session_state['results'][i] = corrected
                st.success('Correction saved. Reviewed views and exports use the latest revision.')
                st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.error(str(exc))
    with st.expander('Optional source-specific classification'):
        task = st.selectbox('Compatible source taxonomy', ['None', 'Fire-door classes', 'FAA part condition', 'PHMSA cause'])
        paths = {'Fire-door classes': 'fire-door-tfidf-v1', 'FAA part condition': 'faa-part-condition-tfidf-v1', 'PHMSA cause': 'phmsa-cause-tfidf-v1'}
        compatible = st.checkbox('This report uses the selected source taxonomy')
        if st.button('Classify document', disabled=task == 'None' or not compatible):
            try:
                prediction = predict(joblib.load(ROOT / 'models' / paths[task] / 'model.joblib'), record.clean_text)
                st.session_state['classification'] = {'identity': (record.record_id, record.document_metadata.get('run_id'), task), 'prediction': prediction}
            except (OSError, ValueError) as exc:
                st.warning(f'Classifier unavailable: {exc}')
        saved = st.session_state.get('classification')
        if saved and saved['identity'] == (record.record_id, record.document_metadata.get('run_id'), task):
            st.write(saved['prediction'])
            st.caption('Source-specific classification score; not validated for arbitrary industries.')


def downloads(records):
    st.download_button('Download findings (CSV)', export_csv(records), 'inspectra_findings.csv', 'text/csv')
    st.download_button('Download findings (JSON)', export_json(records, versioned=True), 'inspectra_findings.json', 'application/json')
    st.download_button('Download summary (HTML)', export_html(records), 'inspectra_summary.html', 'text/html')


def overview_page(records, rows):
    summary = analytics.overview(records, rows)
    for column, (name, value) in zip(st.columns(5), summary.items(), strict=True):
        column.metric(name.replace('_', ' ').title(), value)
    severities = Counter(s for row in rows if row['assertion'] == 'present' for s in row['severity'])
    selected = bar([{'severity': label, 'count': severities[label]} for label in ['critical', 'severe', 'major', 'minor', 'Unknown'] if severities[label]], 'severity', 'count', 'Explicit linked severity', 'severity_chart')
    evidence_table(records, rows, ("severity", selected) if selected else None)


def defects_page(records, rows):
    counts = Counter(row['defect'] for row in rows)
    ordered = [{'defect': label, 'count': count} for label, count in counts.most_common()]
    selected = bar(ordered, 'defect', 'count', 'Defect frequency (ordered)', 'defect_pareto')
    if ordered:
        total, running = sum(r['count'] for r in ordered), 0
        for row in ordered:
            running += row['count']
            row['cumulative_percent'] = 100 * running / total
        line = go.Figure(go.Scatter(x=[r['defect'] for r in ordered], y=[r['cumulative_percent'] for r in ordered], mode='lines+markers'))
        line.update_layout(title='Pareto cumulative share', yaxis_title='Cumulative percent')
        st.plotly_chart(line, width='stretch')
    field = st.selectbox('Linked heatmap evidence', ['material', 'component'])
    cells = heatmap(analytics.heatmap_cells(rows, field), f'Linked {field} × defect', 'linked_heatmap')
    narrowed = [r for r in rows if not cells or any(group in r[field] and defect == r['defect'] for group, defect in cells)]
    evidence_table(records, narrowed, ('defect', selected) if selected else None)
    with st.expander('Report-level co-occurrence (does not establish a relationship)'):
        table(analytics.cooccurrence_cells(records, field.upper()))


def vendors_page(records, rows):
    st.caption('Affected-report rates describe reported inspection outcomes. Report volume and sampling can differ across vendors; these are not defective-item rates or safety rankings.')
    rates = analytics.vendor_rates(records, rows)
    table(rates)
    selected = bar(rates, 'vendor', 'affected_report_rate', 'Affected reports / inspected reports (%)', 'vendor_rates')
    cells = heatmap(analytics.heatmap_cells(rows, 'vendor'), 'Vendor × defect', 'vendor_heatmap')
    narrowed = [r for r in rows if not cells or [r['vendor'], r['defect']] in cells]
    evidence_table(records, narrowed, ('vendor', selected) if selected else None)


def trends_page(records, rows):
    trends, undated = analytics.monthly_trends(records, rows)
    st.caption(f'{undated} undated reports excluded. All dated inspected reports remain in rate denominators.')
    field = st.selectbox('Trend measure', ['active_defects', 'affected_reports', 'affected_report_rate'])
    selected = []
    if trends:
        figure = go.Figure(go.Scatter(x=[r['month'] for r in trends], y=[r[field] for r in trends],
            customdata=[r['month'] for r in trends], mode='lines+markers'))
        figure.update_layout(title='Monthly inspection outcomes', yaxis_title=field.replace('_', ' ').title())
        event = st.plotly_chart(figure, key='monthly_chart', on_select='rerun', width='stretch')
        selected = [p['customdata'] for p in event.selection.points if 'customdata' in p]
    else:
        st.info('No dated reports for the current scope.')
    monthly = [r for r in rows if not selected or (r['date'] and r['date'][:7] in selected)]
    timeline = [r for r in rows if r['recurrence']]
    st.subheader('Reliably linked recurrence')
    table(timeline)
    if timeline:
        figure = go.Figure(go.Scatter(x=[r['date'] for r in timeline], y=[r['vendor'] for r in timeline],
            mode='markers', text=[r['defect'] for r in timeline], customdata=[r['recurrence'] for r in timeline],
            hovertemplate='%{y} · %{text}<br>%{x}<br>Earlier findings: %{customdata}<extra></extra>'))
        st.plotly_chart(figure, key='recurrence_timeline', width='stretch')
    st.caption('Recurrence requires vendor, asset/batch, category, and earlier report dates. Missing linkage is not evidence of no recurrence.')
    evidence_table(records, monthly)


def queue_page(library, records, rows, settings):
    queue = analytics.review_queue(records, rows)
    table(queue)
    ages = Counter('0–7 days' if r['age_days'] <= 7 else '8–30 days' if r['age_days'] <= 30 else '31+ days' for r in queue)
    bar([{'age': k, 'count': v} for k, v in ages.items()], 'age', 'count', 'Review backlog age', 'backlog_age')
    candidates = [r for r in records if any(q['record_id'] == r.record_id for q in queue)]
    if candidates:
        show_record(select_record(candidates), library, settings)
    with st.expander('Review history and legacy import'):
        table(library.history())
        if st.button('Import legacy reviews'):
            st.write(library.import_legacy(ROOT / 'data/annotations/reviews.jsonl'))
        backup_name = st.text_input('New backup filename', value='inspectra-backup.sqlite3')
        if st.button('Create database backup'):
            try:
                library.backup(library.path.parent / Path(backup_name).name)
                st.success('Backup created')
            except (ValueError, OSError) as exc:
                st.error(str(exc))


def quality_page(records):
    st.info('Human-validated extraction accuracy across unseen vendors and industries remains pending.')
    versions = Counter((r.document_metadata.get('extractor_version', 'unknown'), r.document_metadata.get('extraction_mode', 'unknown')) for r in records)
    table([{'version': v, 'mode': mode, 'narratives': n} for (v, mode), n in versions.items()])
    files = ['fire_door_baseline.json', 'faa-part-condition_baseline.json', 'phmsa-cause_baseline.json', 'silver_ner_evaluation.json', 'provisional_hybrid_calibration_v2.json', 'generalisation_evaluation.json']
    for path in sorted((ROOT / "reports").glob("*.json")):
        if path.name not in files:
            try:
                artifact = json.loads(path.read_text())
                if artifact.get("status") == "measured" and "partition_mode" in artifact:
                    files.append(path.name)
            except (ValueError, OSError):
                pass
    for name in files:
        path = ROOT / 'reports' / name
        if path.exists():
            with st.expander(name):
                st.caption('Source-specific or provisional results apply only to their stated task and evaluation data.')
                st.json(json.loads(path.read_text()))
    with st.expander('Research corpus coverage (separate from vendor library)'):
        path = ROOT / 'reports/source_wide_analytics.json'
        if path.exists():
            st.json(json.loads(path.read_text()))
    st.caption('Supported: English machine-readable PDF, DOCX, TXT, CSV, TSV, XLSX. Scanned PDFs require OCR outside this scope. Optional classifiers require compatible source taxonomies.')


def main(page: str | None = None):
    st.set_page_config(page_title='Inspectra', page_icon='🔎', layout='wide')
    library = Library(Path(os.environ.get('INSPECTRA_DB', 'data/local/inspectra.sqlite3')))
    st.title('🔎 Inspectra')
    st.caption('Review material defects from English vendor inspection reports across industries.')
    choice = st.sidebar.selectbox('Optional terminology pack', ['General', 'Construction', 'Aviation', 'Pipeline'])
    other = st.sidebar.text_input('Other industry (optional)')
    pack_text = st.sidebar.text_input('Additional YAML pack paths (comma-separated)')
    hybrid = st.sidebar.toggle('Provisional NER coverage', value=False, disabled=not (ROOT / 'models/silver-ner-v1').exists())
    enabled = st.sidebar.toggle('Review priorities', value=True)
    original = st.sidebar.toggle('Original extraction view', value=False)
    if english_model() is None:
        st.sidebar.warning('Rules-only coverage: pinned English model unavailable')
    settings = {'domain': other.strip().casefold() or choice.lower(), 'hybrid': hybrid,
                'packs': tuple(p.strip() for p in pack_text.split(',') if p.strip())}
    records = with_recurrence([prioritize(r, enabled) for r in library.records(reviewed=not original)])
    scope, rows, filters = filter_sidebar(records)
    settings['priority'] = enabled
    def render(name):
        st.header(name)
        st.caption(f'{len({analytics.report_key(r) for r in scope})} inspected reports in metadata scope; defect filters narrow findings only.')
        if name == 'Report explorer':
            report_explorer(library, scope, rows, settings, filters)
        elif name == 'Overview':
            overview_page(scope, rows)
        elif name == 'Defect analysis':
            defects_page(scope, rows)
        elif name == 'Vendor comparison':
            vendors_page(scope, rows)
        elif name == 'Trends':
            trends_page(scope, rows)
        elif name == 'Review queue':
            queue_page(library, scope, rows, settings)
        else:
            quality_page(scope)
        if name not in {'Report explorer', 'Model quality'}:
            downloads(analytics.export_scope(scope, rows))
    if page is not None:
        render(page)
    else:
        navigation = st.navigation([st.Page(lambda name=name: render(name), title=name,
            url_path=name.lower().replace(' ', '-'), default=name == 'Report explorer') for name in PAGES])
        navigation.run()
