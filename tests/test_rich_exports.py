import csv
import io
import json

from inspection_nlp.documents import parse_document
from inspection_nlp.export import export_csv, export_html, export_json
from inspection_nlp.extraction import extract
from inspection_nlp.schemas import Record


def test_export_schema_and_formula_safety():
    r = extract(
        parse_document(
            b"<script>ignore</script> Steel spindle cracked.",
            "report.txt",
            report_metadata={"vendor": "=EVIL()", "asset_id": "@A"},
        )[0]
    )
    data = json.loads(export_json([r], versioned=True))
    assert data["export_schema_version"] == "inspectra-export-v2"
    assert Record.model_validate(data["records"][0]).findings
    row = next(csv.DictReader(io.StringIO(export_csv([r]))))
    assert row["vendor"] == "'=evil()"
    assert row["asset_id"] == "'@A"
    assert row["linked_evidence"]
    html = export_html([r])
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Inspected reports" in html and "Priority" in html


def test_synthetic_vendor_demo():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "samples/vendor_demo/synthetic_reports.csv"
    records = parse_document(
        path.read_bytes(),
        path.name,
        text_column="Inspection",
        metadata_columns={"vendor": "Company", "report_date": "InspectionDate"},
    )
    assert len(records) == 7
    assert len({r.report_metadata["vendor"] for r in records}) == 3
    assert any(extract(r).review_candidates for r in records)
