import csv

import pytest
from openpyxl import Workbook
from pydantic import ValidationError

from inspection_nlp.ingestion import load_source
from inspection_nlp.preprocessing import prepare_text
from inspection_nlp.schemas import Entity
from inspection_nlp.splits import assign_splits


def source(tmp_path, name, rows, delimiter=","):
    path = tmp_path / name
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    return list(load_source(path))


def test_faa_features_and_provenance(tmp_path):
    records = source(
        tmp_path,
        "SDR-2024.csv",
        [
            {
                "OperatorControlNumber": "A1",
                "Discrepancy": "Pump inspected.",
                "PartCondition": "CRACKED",
            }
        ],
    )
    record = records[0]
    assert record.clean_text == "Pump inspected."
    assert record.structured_source_fields["PartCondition"] == "CRACKED"
    assert record.source_record_id == "A1"
    assert len(record.source_sha256) == 64
    assert record.mapping_status == "review_required"


@pytest.mark.parametrize("legacy", [False, True])
def test_phmsa_event_grouping(tmp_path, legacy):
    name = "incident_mar2004_dec2009.txt" if legacy else "incident_current.txt"
    id_col = "RPTID" if legacy else "REPORT_NUMBER"
    records = source(
        tmp_path,
        name,
        [
            {id_col: "100", "NARRATIVE": "A leak occurred.", "CAUSE": "X"},
            {id_col: "100", "NARRATIVE": "Supplemental leak report.", "CAUSE": "Y"},
        ],
        "\t",
    )
    assign_splits(records)
    assert records[0].split == records[1].split
    assert records[0].source_event_id == records[1].source_event_id
    assert records[0].record_id != records[1].record_id
    assert ("legacy" in records[0].schema_version) == legacy


def test_fire_door_empty_and_labels(tmp_path):
    path = tmp_path / "training.xlsx"
    workbook = Workbook()
    workbook.active.append(
        ["Apartments", "Korean", "English", "Classification_Korean", "Classification_English"]
    )
    workbook.active.append(["A", "", "Door dented.", "", "dent"])
    workbook.active.append(["B", "", None, "", "scratch"])
    workbook.save(path)
    records = list(load_source(path))
    assert records[0].clean_text == "Door dented."
    assert records[0].document_metadata["original_split"] == "training"
    assert records[1].document_metadata["exclusion_reason"] == "empty_narrative"


def test_duplicate_bridge_and_heldout(tmp_path):
    records = source(
        tmp_path,
        "SDR.csv",
        [
            {"OperatorControlNumber": "1", "Discrepancy": "Same text"},
            {"OperatorControlNumber": "2", "Discrepancy": " SAME  TEXT "},
            {"OperatorControlNumber": "2", "Discrepancy": "Changed text"},
        ],
    )
    records[-1].domain = "pipeline"
    assign_splits(records, held_out_domain="pipeline")
    assert {r.split for r in records} == {"test"}
    before = {r.record_id: r.split for r in records}
    assign_splits(list(reversed(records)), held_out_domain="pipeline")
    assert before == {r.record_id: r.split for r in records}


@pytest.mark.parametrize(
    "pii",
    [
        "a.person@example.com",
        "(212) 555-0123",
        "123 Main Street",
        "38.123456, -77.123456",
        "latitude: 38.123456",
    ],
)
def test_privacy(pii):
    text, flagged = prepare_text(f"Leak near {pii}.")
    assert flagged
    assert pii not in text
    assert "[REDACTED]" in text


def test_normalization_and_span_validation(tmp_path):
    text, flagged = prepare_text(" No\n crack\tobserved. ")
    assert text == "No crack observed."
    assert not flagged
    record = source(tmp_path, "SDR.csv", [{"OperatorControlNumber": "1", "Discrepancy": text}])[0]
    entity = Entity(
        label="DEFECT",
        text="crack",
        evidence_start=3,
        evidence_end=8,
        assertion="negated",
        confidence=1,
        extraction_method="human",
    )
    payload = record.model_dump()
    payload["entities"] = [entity.model_dump()]
    assert type(record).model_validate(payload).entities[0].assertion == "negated"
    payload["entities"][0]["evidence_start"] = 0
    with pytest.raises(ValidationError):
        type(record).model_validate(payload)


def test_missing_schema_rejected(tmp_path):
    with pytest.raises(ValueError, match="missing required columns"):
        source(tmp_path, "SDR.csv", [{"Wrong": "x"}])


def test_local_english_workbook_variant(tmp_path):
    path = tmp_path / "test.xlsx"
    workbook = Workbook()
    workbook.active.append(["Apartments", "English", "Classification_English"])
    workbook.active.append(["A", "Seal missing.", "absence"])
    workbook.save(path)
    assert next(load_source(path)).schema_version == "fire_door_english_v1"


def test_phmsa_windows_encoding(tmp_path):
    path = tmp_path / "current.txt"
    path.write_bytes("REPORT_NUMBER\tNARRATIVE\n1\tValve “failed”.\n".encode("cp1252"))
    record = next(load_source(path))
    assert record.clean_text == "Valve “failed”."
    assert record.document_metadata["encoding"] == "cp1252"

def test_dashboard_shell():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app/streamlit_app.py").run()
    assert not app.exception
    app.text_area[0].input("Unknown widget failed.").run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    assert not app.exception
    assert any("Needs review" in element.value for element in app.subheader)


def test_dashboard_reanalyzes_after_domain_change():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app/streamlit_app.py").run()
    app.text_area[0].input("Valve cracked.").run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    assert not app.exception
    app.sidebar.selectbox[0].select("Pipeline").run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    assert not app.exception
