"""Inspectra user-facing inspection narrative dashboard."""

import json
from collections import Counter
from pathlib import Path
from zipfile import BadZipFile

import joblib
import streamlit as st

from inspection_nlp.analytics import review_summary
from inspection_nlp.classification import predict
from inspection_nlp.documents import parse_document
from inspection_nlp.export import export_csv, export_json
from inspection_nlp.extraction import extract
from inspection_nlp.hybrid import extract_hybrid
from inspection_nlp.reviews import append_review, review_history, review_payload

st.set_page_config(page_title="Inspectra", page_icon="🔎", layout="wide", initial_sidebar_state="expanded")


def donut(data, category, value, title):
    if not data:
        st.info("No data available yet.")
        return
    st.vega_lite_chart(
        data,
        {
            "title": title,
            "mark": {"type": "arc", "innerRadius": 52, "tooltip": True},
            "encoding": {
                "theta": {"field": value, "type": "quantitative"},
                "color": {"field": category, "type": "nominal", "legend": {"title": None}},
                "tooltip": [
                    {"field": category, "type": "nominal", "title": category.title()},
                    {"field": value, "type": "quantitative", "title": "Count"},
                ],
            },
            "height": 300,
        },
        width="stretch",
    )


def bars(data, category, value, title, color="#00A6A6"):
    if not data:
        st.info("No data available yet.")
        return
    st.vega_lite_chart(
        data,
        {
            "title": title,
            "mark": {"type": "bar", "cornerRadiusEnd": 4, "color": color},
            "encoding": {
                "x": {"field": value, "type": "quantitative", "title": "Records"},
                "y": {"field": category, "type": "nominal", "sort": "-x", "title": None},
                "tooltip": [{"field": category, "type": "nominal"}, {"field": value, "type": "quantitative"}],
            },
            "height": 320,
        },
        width="stretch",
    )


@st.cache_resource
def load_fire_door_model():
    return joblib.load("models/fire-door-tfidf-v1/model.joblib")


@st.cache_data
def source_analytics():
    path = Path("reports/source_wide_analytics.json")
    return json.loads(path.read_text()) if path.exists() else {"domains": {}}


st.title("🔎 Inspectra")
st.caption("Turn inspection narratives into structured, reviewable findings.")

with st.sidebar:
    st.header("Analysis settings")
    choice = st.selectbox("Inspection domain", ["Auto / General", "Construction", "Aviation", "Pipeline"], key="domain_choice")
    domain = "general" if choice == "Auto / General" else choice.lower()
    silver_model_path = Path("models/silver-ner-v1")
    use_silver_ner = st.toggle(
        "Enhanced finding coverage",
        value=False,
        disabled=not silver_model_path.exists(),
        help="Adds provisional pattern coverage. Every result still requires review.",
    )
    st.divider()
    st.caption("Inspectra supports machine-readable PDF, DOCX, TXT, CSV, TSV, and XLSX files.")
    st.caption("Do not upload sensitive material unless you are authorized to process it.")

analyze_tab, portfolio_tab, history_tab, help_tab = st.tabs(
    ["Analyze report", "Portfolio insights", "Review history", "How it works"]
)

with analyze_tab:
    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        st.subheader("Add an inspection report")
        upload = st.file_uploader("Upload a file", type=["pdf", "docx", "csv", "xlsx", "tsv", "txt"])
        paste = st.text_area("Or paste a narrative", height=130, placeholder="Paste an inspection narrative…")
        text_column = st.text_input("Narrative column", help="Required only for CSV, TSV, and XLSX files.")
        tabular_txt = st.checkbox("My TXT file is tabular")
        encoding = st.selectbox("Text encoding", ["utf-8-sig", "cp1252"])
        run = st.button("Analyze findings", type="primary", width="stretch")
    with right:
        st.subheader("What you receive")
        st.markdown("""
        - Structured findings with evidence and status
        - Visual distributions of finding types and assertions
        - Exportable findings for follow-up workflows
        - A separate correction history that never changes the source file
        """)
        st.info("Findings support review; they do not determine compliance or engineering risk.")

    if run:
        if upload is None and not paste.strip():
            st.warning("Add a report or paste a narrative before analyzing.")
        else:
            try:
                records = parse_document(
                    upload.getvalue() if upload else paste.encode(),
                    upload.name if upload else "pasted.txt",
                    domain=domain,
                    text_column=text_column or None,
                    tabular_txt=tabular_txt,
                    encoding=encoding if upload else "utf-8-sig",
                )
                with st.spinner("Finding evidence…"):
                    results = [
                        extract_hybrid(record, silver_model_path) if use_silver_ner else extract(record)
                        for record in records
                    ]
                st.session_state["results"] = results
                st.session_state.pop("fire_door_prediction", None)
            except (ValueError, UnicodeError, RuntimeError, BadZipFile, KeyError) as exc:
                st.session_state.pop("results", None)
                st.error(f"We could not analyze this report: {exc}")

    results = st.session_state.get("results", [])
    if results:
        summary = review_summary(results)
        metric_columns = st.columns(4)
        for column, label, value in zip(
            metric_columns,
            ["Narratives", "Findings", "Needs review", "No supported finding"],
            [summary["records"], summary["entities"], summary["review_required"], summary["unmapped"]],
            strict=True,
        ):
            column.metric(label, value)
        record_index = st.selectbox("Narrative", range(len(results)), format_func=lambda i: f"Narrative {i + 1}")
        record = results[record_index]
        state = "Needs review" if record.mapping_status == "review_required" else "No supported finding"
        st.subheader(f"Findings · {state}")
        finding_rows = [
            {
                "Finding type": entity.label.replace("_", " ").title(),
                "Evidence": entity.text,
                "Status": entity.assertion.title(),
                "Confidence": f"{entity.confidence:.0%}",
            }
            for entity in record.entities
        ]
        st.dataframe(finding_rows, hide_index=True, width="stretch")
        chart_left, chart_right = st.columns(2)
        all_entities = [entity for item in results for entity in item.entities]
        with chart_left:
            donut(
                [{"type": name.replace("_", " ").title(), "count": count} for name, count in Counter(e.label for e in all_entities).items()],
                "type", "count", "Finding types",
            )
        with chart_right:
            donut(
                [{"status": name.title(), "count": count} for name, count in Counter(e.assertion for e in all_entities).items()],
                "status", "count", "Finding status",
            )
        st.download_button("Download findings (CSV)", export_csv(results), "inspectra_findings.csv", "text/csv")
        st.download_button("Download findings (JSON)", export_json(results), "inspectra_findings.json", "application/json")

        with st.expander("Review and correct findings"):
            st.caption("Corrections are stored separately from the original report.")
            editor_rows = st.data_editor(
                [entity.model_dump() for entity in record.entities],
                disabled=["text", "confidence", "extraction_method"],
                key=f"review_{record.record_id}",
                hide_index=True,
                width="stretch",
            )
            review_note = st.text_area("Review note", key=f"note_{record.record_id}")
            if st.button("Save correction", key=f"save_{record.record_id}"):
                try:
                    payload = review_payload(record, editor_rows.to_dict("records"), review_note)
                    append_review(Path("data/annotations/reviews.jsonl"), payload)
                    st.success("Correction saved to review history.")
                except (KeyError, TypeError, ValueError) as exc:
                    st.error(f"We could not save this correction: {exc}")

        if domain == "construction":
            with st.expander("Fire-door finding category"):
                if st.button("Classify document", key="fire_door_classify"):
                    try:
                        st.session_state["fire_door_prediction"] = predict(load_fire_door_model(), record.clean_text)
                    except FileNotFoundError:
                        st.warning("The local fire-door classifier is not available.")
                prediction = st.session_state.get("fire_door_prediction")
                if prediction:
                    st.metric("Suggested category", prediction["label"], f"{prediction['score']:.0%} score")
                    st.caption("This score is not calibrated and should be reviewed.")

with portfolio_tab:
    st.subheader("Portfolio coverage")
    analytics = source_analytics()
    domains = analytics.get("domains", {})
    coverage = [
        {"domain": name.title(), "records": value["records"], "event groups": value["event_deduplicated_records"], "mean words": value["mean_words"]}
        for name, value in domains.items()
    ]
    metrics = st.columns(3)
    for column, row in zip(metrics, coverage, strict=False):
        column.metric(row["domain"], f"{row['records']:,}", f"{row['event groups']:,} grouped events")
    bars(coverage, "domain", "records", "Source records by domain")
    if domains:
        selected = st.selectbox("Explore a source", list(domains), format_func=str.title)
        details = domains[selected]
        labels = [{"label": label, "count": count} for label, count in details["source_label_counts"].items()]
        left, right = st.columns(2)
        with left:
            bars(labels[:15], "label", "count", f"Most common {selected} categories")
        with right:
            donut(labels[:8], "label", "count", f"Leading {selected} categories")
        st.caption("These counts describe report volume and categories, not risk, severity, or performance.")

with history_tab:
    st.subheader("Saved corrections")
    try:
        history = review_history(Path("data/annotations/reviews.jsonl"))
        if history:
            rows = [
                {"Reviewed": item["reviewed_at"], "Domain": item["domain"].title(), "Findings": len(item["corrected_entities"]), "Note": item["note"]}
                for item in history
            ]
            st.dataframe(rows, hide_index=True, width="stretch")
            donut(
                [{"domain": domain.title(), "count": count} for domain, count in Counter(item["domain"] for item in history).items()],
                "domain", "count", "Corrections by domain",
            )
        else:
            st.info("Corrections saved from the review panel will appear here.")
    except ValueError as exc:
        st.error(f"We could not load correction history: {exc}")

with help_tab:
    st.subheader("Use Inspectra in three steps")
    st.markdown("1. Choose the closest inspection domain and add a report.\n2. Review structured findings and their status.\n3. Save corrections or export findings for your workflow.")
    st.subheader("Important limits")
    st.markdown("Inspectra identifies configured evidence patterns. It does not replace qualified inspection, determine regulatory compliance, or make risk decisions. Review every finding before acting on it.")
