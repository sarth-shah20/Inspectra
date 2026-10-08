from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app/streamlit_app.py'


def test_save_and_invalidate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    app.text_area[0].set_value('Unknown widget failed.').run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['results']
    app.button[1].click().run()
    assert not app.exception
    assert (tmp_path / 'data/annotations/reviews.jsonl').exists()
    app.text_area[0].set_value('Changed report.').run()
    assert 'results' not in app.session_state


def test_empty_input_and_domain_change(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    assert app.warning
    app.text_area[0].set_value('Valve cracked.').run()
    app.button[0].click().run()
    app.sidebar.selectbox[0].select('Pipeline').run()
    assert 'results' not in app.session_state
