import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import speech_text
from review import intros_file, server

FIXTURES = Path(__file__).parent / "fixtures"


def _client(tmp_path, name):
    d = Path(shutil.copytree(FIXTURES / name, tmp_path / name))
    return TestClient(server.create_app(d, tmp_path)), d


def test_page_is_served(tmp_path):
    c, _ = _client(tmp_path, "unbuilt")
    r = c.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_data_for_unbuilt(tmp_path):
    c, _ = _client(tmp_path, "unbuilt")
    data = c.get("/api/data").json()
    assert data["has_tutor"] is False and data["intros"] is None


def test_data_has_the_sentences_the_app_adds_to_the_introduction(tmp_path):
    import intro_notes
    c, _ = _client(tmp_path, "unbuilt")
    assert c.get("/api/data").json()["intro_added"] == [intro_notes.ARITHMETIC_NOTE, intro_notes.MIC_NOTE]


def test_bad_plan_is_one_sentence(tmp_path):
    c, d = _client(tmp_path, "unbuilt")
    plan = json.loads((d / "review.json").read_text())
    del plan["title"]
    (d / "review.json").write_text(json.dumps(plan))
    r = c.get("/api/data")
    assert r.status_code == 422
    assert "title" in r.json()["error"] and "Traceback" not in r.text


def test_save_round_trip(tmp_path):
    c, d = _client(tmp_path, "built")
    data = c.get("/api/data").json()
    intros = data["intros"]
    intros["modules"][0]["spoken"] = "A new spoken intro."
    r = c.put("/api/save", json={"version": data["version"],
                                 "edits": {"intro_status": "reviewed", "modules": {"1": {"notes": "New note."}}},
                                 "intros": intros})
    assert r.status_code == 200
    saved = json.loads((d / "review.json").read_text())
    assert saved["modules"][0]["notes"] == "New note." and saved["intro_status"] == "reviewed"
    assert intros_file.read(d / "content" / "module-intros.md")["modules"][0]["spoken"] == "A new spoken intro."
    assert r.json()["version"] != data["version"]


def test_stale_save_refused(tmp_path):
    c, d = _client(tmp_path, "built")
    data = c.get("/api/data").json()
    on_disk = json.loads((d / "review.json").read_text())
    on_disk["notes"] = "Claude changed this."
    (d / "review.json").write_text(json.dumps(on_disk))
    r = c.put("/api/save", json={"version": data["version"], "edits": {"notes": "Mine."}, "intros": None})
    assert r.status_code == 409
    assert r.json()["error"] == "The files changed since you opened this page. Reload to see the new version."
    assert json.loads((d / "review.json").read_text())["notes"] == "Claude changed this."


def test_save_refuses_a_bad_edit(tmp_path):
    c, _ = _client(tmp_path, "built")
    v = c.get("/api/data").json()["version"]
    r = c.put("/api/save", json={"version": v, "edits": {"modules": {"1": {"tools": []}}}, "intros": None})
    assert r.status_code == 422 and "tools" in r.json()["error"]


def test_listen_needs_a_built_tutor(tmp_path):
    c, _ = _client(tmp_path, "unbuilt")
    r = c.post("/api/listen", json={"text": "Hello."})
    assert r.status_code == 409


class FakeSpeech:
    ready = True
    error = None

    def __init__(self):
        self.said = []

    async def synth(self, text):
        self.said.append(text)
        return b"RIFF"


def test_listen_speaks_the_spoken_form(tmp_path, monkeypatch):
    fake = FakeSpeech()
    monkeypatch.setattr(server, "make_speech", lambda tutor_dir: fake)
    c, _ = _client(tmp_path, "built")
    text = "Delta t = T/n, about 2%"
    r = c.post("/api/listen", json={"text": text})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert fake.said == [speech_text.spoken_form(text)]


def test_listen_while_loading(tmp_path, monkeypatch):
    fake = FakeSpeech()
    fake.ready = False
    monkeypatch.setattr(server, "make_speech", lambda tutor_dir: fake)
    c, _ = _client(tmp_path, "built")
    r = c.post("/api/listen", json={"text": "Hi."})
    assert r.status_code == 503 and "loading" in r.json()["error"]


def test_plot_preview(tmp_path):
    c, _ = _client(tmp_path, "built")
    r = c.post("/api/plot", json={"module": 1, "plot": 0})
    assert r.status_code == 200 and r.json() == {"data": [], "layout": {}}


def test_tests_need_a_built_tutor(tmp_path):
    c, _ = _client(tmp_path, "unbuilt")
    assert c.post("/api/tests").status_code == 409


def test_unexpected_plan_problem_is_a_sentence(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, "unbuilt")
    def boom(*a):
        raise AttributeError("'str' object has no attribute 'setdefault'")
    monkeypatch.setattr(server.plan, "page_data", boom)
    r = c.get("/api/data")
    assert r.status_code == 422 and r.json()["error"].startswith("review.json has a problem Claude must fix")


def test_plot_preview_picks_up_edits_to_the_tutor_s_other_modules(tmp_path):
    # topic.py imports a helper; after the helper changes on disk, the next preview uses it.
    c, d = _client(tmp_path, "built")
    (d / "preview_helper.py").write_text("TITLE = 'old'\n")
    (d / "topic.py").write_text("import preview_helper\n\n"
                                "def make_plot(args, state=None):\n"
                                "    return '', {'plot': {'data': [], 'layout': {'title': preview_helper.TITLE}}}\n")
    assert c.post("/api/plot", json={"module": 1, "plot": 0}).json()["layout"]["title"] == "old"
    (d / "preview_helper.py").write_text("TITLE = 'new'\n")
    assert c.post("/api/plot", json={"module": 1, "plot": 0}).json()["layout"]["title"] == "new"


def test_plot_previews_at_the_same_time_all_draw(tmp_path):
    # The page asks for a module's plots at once; each request reloads the tutor's modules.
    from concurrent.futures import ThreadPoolExecutor
    c, d = _client(tmp_path, "built")
    (d / "preview_helper.py").write_text("import time\ntime.sleep(0.02)\nTITLE = 'ok'\n")
    (d / "topic.py").write_text("import preview_helper\n\n"
                                "def make_plot(args, state=None):\n"
                                "    return '', {'plot': {'data': [], 'layout': {'title': preview_helper.TITLE}}}\n")
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda _: c.post("/api/plot", json={"module": 1, "plot": 0}).status_code, range(12)))
    assert codes == [200] * 12
