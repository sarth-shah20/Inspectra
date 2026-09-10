import json
from pathlib import Path
from zipfile import BadZipFile

import joblib
import streamlit as st

from inspection_nlp.analytics import entity_counts, review_summary
from inspection_nlp.classification import predict
from inspection_nlp.documents import parse_document
from inspection_nlp.export import export_csv, export_json, highlight
from inspection_nlp.extraction import extract
from inspection_nlp.hybrid import extract_hybrid
from inspection_nlp.reviews import append_review, review_payload

st.set_page_config(page_title="Inspectra", layout="wide")
st.title("Inspectra")
st.write("Extract supported evidence from inspection, maintenance, and incident narratives.")
choice = st.selectbox("Domain", ["Auto/General", "Construction", "Aviation", "Pipeline"])
domain = "general" if choice == "Auto/General" else choice.lower()
st.caption("Auto/General uses shared vocabulary. Choose a domain to add its configured terms.")


@st.cache_resource
def load_fire_door_model():
    return joblib.load("models/fire-door-tfidf-v1/model.joblib")


silver_model_path = Path("models/silver-ner-v1")
use_silver_ner = st.checkbox(
    "Add provisional silver NER spans",
    disabled=not silver_model_path.exists(),
    help="Uses an AI-silver-label model. It is not human-validated and all spans require review.",
)
if not silver_model_path.exists():
    st.caption("Optional silver NER model is not present locally; rules extraction remains available.")

upload = st.file_uploader("Upload a report", type=["pdf", "docx", "csv", "xlsx", "tsv", "txt"])
text_column = st.text_input("Narrative column for tabular files", value="")
tabular_txt = st.checkbox("TXT contains a tab-delimited table")
encoding = st.selectbox("Text file encoding", ["utf-8-sig", "cp1252"])
text = st.text_area("Narrative")
if upload is not None and text.strip():
    st.caption("The uploaded report takes precedence over pasted text.")
if upload is not None or text.strip():
    try:
        records = parse_document(
            upload.getvalue() if upload else text.encode(),
            upload.name if upload else "pasted.txt",
            domain=domain,
            text_column=text_column or None,
            tabular_txt=tabular_txt,
            encoding=encoding if upload else "utf-8-sig",
        )
        st.text(records[0].display_text)
        signature = (
            tuple((record.record_id, record.clean_text) for record in records),
            domain,
            text_column,
            tabular_txt,
            encoding,
            use_silver_ner,
        )
        if st.session_state.get("input_signature") != signature:
            st.session_state.pop("results", None)
            st.session_state.pop("fire_door_prediction", None)
            st.session_state["input_signature"] = signature
        if st.button("Extract evidence"):
            with st.spinner("Extracting evidence…"):
                results = [
                    extract_hybrid(record, silver_model_path) if use_silver_ner else extract(record)
                    for record in records
                ]
            st.session_state["results"] = results
    except (ValueError, UnicodeError, RuntimeError, BadZipFile, KeyError) as exc:
        st.session_state.pop("results", None)
        st.error(f"Could not process this input: {exc}")
else:
    st.session_state.pop("results", None)
    st.session_state.pop("fire_door_prediction", None)

results = st.session_state.get("results", [])
if results:
    index = st.selectbox("Record", range(len(results)), format_func=lambda i: f"Record {i + 1}")
    record = results[index]
    st.write(f"Mapping status: {record.mapping_status.upper()}")
    st.markdown(highlight(record), unsafe_allow_html=True)
    st.dataframe([entity.model_dump() for entity in record.entities], hide_index=True)
    if not record.entities:
        st.info("No supported evidence matched. Review unfamiliar terminology manually.")
    st.download_button("Download JSON", export_json(results), "inspectra.json", "application/json")
    st.download_button("Download CSV", export_csv(results), "inspectra.csv", "text/csv")
    st.subheader("Human review")
    st.caption("Edits are saved separately and never overwrite source or automated records.")
    editor_rows = st.data_editor(
        [entity.model_dump() for entity in record.entities],
        disabled=["text", "confidence", "extraction_method"],
        key=f"review_{record.record_id}",
        hide_index=True,
    )
    review_note = st.text_area("Review note", key=f"note_{record.record_id}")
    if st.button("Save human review"):
        try:
            rows = editor_rows.to_dict("records")
            payload = review_payload(record, rows, review_note)
            append_review(Path("data/annotations/reviews.jsonl"), payload)
            st.success("Saved separately to the local reviewed-data file.")
        except (KeyError, TypeError, ValueError) as exc:
            st.error(f"Could not save review: {exc}")
    if domain == "construction":
        st.subheader("Fire-door document class")
        st.caption("This is the eight-class source taxonomy, separate from extracted evidence.")
        if st.button("Classify as a fire-door finding"):
            try:
                prediction = predict(load_fire_door_model(), record.clean_text)
                st.session_state["fire_door_prediction"] = prediction
            except FileNotFoundError:
                st.warning("Train the local fire-door baseline before classifying documents.")
        prediction = st.session_state.get("fire_door_prediction")
        if prediction:
            st.write(f"Predicted class: {prediction['label']}")
            st.write(f"Raw model score: {prediction['score']:.1%}")
            st.caption(
                "This score is not calibrated. Review unfamiliar wording and low scores manually."
            )
    st.subheader("Analytics for this input")
    summary = review_summary(results)
    columns = st.columns(4)
    for column, (name, value) in zip(columns, summary.items(), strict=True):
        column.metric(name.replace("_", " ").title(), value)
    counts = entity_counts(results)
    if counts:
        st.bar_chart(counts, x="entity", y="count")
    else:
        st.info("No extracted entities to summarize.")
    st.subheader("Saved model evaluations")
    silver_report_path = Path("reports/silver_ner_evaluation.json")
    if silver_report_path.exists():
        silver_report = json.loads(silver_report_path.read_text())
        with st.expander("Provisional silver NER"):
            st.write(f"Silver-label test exact F1: {silver_report['test']['exact_f1']:.4f}")
            st.caption(silver_report["metric_scope"])
    for path in [
        Path("reports/fire_door_baseline.json"),
        Path("reports/faa-part-condition_baseline.json"),
        Path("reports/phmsa-cause_baseline.json"),
    ]:
        if path.exists():
            report = json.loads(path.read_text())
            with st.expander(report["experiment"]):
                st.write(f"Test macro-F1: {report['test']['macro_f1']:.4f}")
                st.write(f"Test weighted-F1: {report['test']['weighted_f1']:.4f}")
                st.caption(
                    "Source-specific document classification; not entity-extraction performance."
                )
st.caption("Rule confidence is uncalibrated. Assertion scope and unfamiliar terms require review.")
st.caption("Privacy review required before sharing. Automated redaction is incomplete.")
st.caption("Machine-readable English reports only. No OCR or certified engineering risk decisions.")
