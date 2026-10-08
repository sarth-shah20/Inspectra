from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app/streamlit_app.py"


def test_save_and_invalidate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    app.text_area[0].set_value("Unknown widget failed.").run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    assert not app.exception
    assert app.session_state["results"]
    next(b for b in app.button if b.label == "Save correction").click().run()
    assert not app.exception
    assert (tmp_path / "data/local/inspectra.sqlite3").exists()
    assert app.session_state["results"][0].label_origin == "human"
    app.text_area[0].set_value("Changed report.").run()
    assert "results" not in app.session_state


def test_empty_input_and_domain_change(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    assert app.warning
    app.text_area[0].set_value("Valve cracked.").run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    app.sidebar.selectbox[0].select("Pipeline").run()
    assert "results" not in app.session_state


def test_review_restart_and_exports(monkeypatch, tmp_path):
    import json

    from inspection_nlp.export import export_json
    from inspection_nlp.storage import Library

    path = tmp_path / "library.sqlite3"
    monkeypatch.setenv("INSPECTRA_DB", str(path))
    app = AppTest.from_file(str(APP)).run()
    app.text_area[0].set_value("Ceramic spindle cracked.").run()
    next(x for x in app.text_input if x.label == "Vendor").set_value("Unseen Textiles").run()
    next(b for b in app.button if b.label == "Analyze findings").click().run()
    r = app.session_state["results"][0]
    next(x for x in app.selectbox if x.label == "Review workflow").select("in_progress").run()
    next(b for b in app.button if b.label == "Save correction").click().run()
    assert not app.exception
    lib = Library(path)
    assert lib.records()[0].report_status == "in_progress"
    from inspection_nlp.reviews import review_payload

    # AppTest does not expose editable grid interactions; exercise its correction service.
    edited = [e.model_dump() for e in r.entities]
    next(e for e in edited if e["label"] == "DEFECT")["assertion"] = "negated"
    lib.save_review(r, review_payload(r, edited, "Negation corrected"))
    reviewed = lib.records()[0]
    assert reviewed.findings[0].defect.assertion == "negated"
    assert lib.records(False)[0].findings[0].defect.assertion == "present"
    exported = json.loads(export_json([reviewed], versioned=True))
    assert exported["records"][0]["findings"][0]["defect"]["assertion"] == "negated"
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert any(x.value == "Findings · Reviewed" for x in restarted.subheader)
