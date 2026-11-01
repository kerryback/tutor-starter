import json
import shutil
from pathlib import Path

import pytest

from review import plan
from review.plan import PlanError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def unbuilt(tmp_path):
    return Path(shutil.copytree(FIXTURES / "unbuilt", tmp_path / "unbuilt"))


@pytest.fixture
def built(tmp_path):
    return Path(shutil.copytree(FIXTURES / "built", tmp_path / "built"))


def _tool(data, name):
    return next(t for m in data["modules"] for t in m["tools"] if t["name"] == name)


def test_load_fills_defaults(unbuilt):
    p = plan.load(unbuilt)
    assert p["modules"][0]["status"] == "open"
    assert p["modules"][0]["examples"] == []
    assert p["modules"][0]["tools"][0]["file"] == "topic.py"
    assert p["modules"][1]["tools"] == []


def test_load_fills_concept_defaults(unbuilt):
    p = plan.load(unbuilt)
    assert p["modules"][0]["concepts"][0]["scripts"][0]["origin"] == "new"
    assert p["modules"][1]["concepts"] == []


def test_load_names_a_concept_without_a_name(unbuilt):
    data = json.loads((unbuilt / "review.json").read_text())
    del data["modules"][0]["concepts"][0]["name"]
    (unbuilt / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match="concept"):
        plan.load(unbuilt)


def test_load_names_the_missing_key(unbuilt):
    data = json.loads((unbuilt / "review.json").read_text())
    del data["title"]
    (unbuilt / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match="title"):
        plan.load(unbuilt)


def test_load_names_the_bad_line(unbuilt):
    (unbuilt / "review.json").write_text('{\n  "tutor": "x",\n  oops\n}')
    with pytest.raises(PlanError) as e:
        plan.load(unbuilt)
    assert "review.json" in str(e.value) and "line 3" in str(e.value)


def test_load_names_a_missing_module_key(unbuilt):
    data = json.loads((unbuilt / "review.json").read_text())
    del data["modules"][1]["title"]
    (unbuilt / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match="title"):
        plan.load(unbuilt)


def test_load_accepts_a_module_without_teaches(built):
    assert "teaches" not in plan.load(built)["modules"][0]


def test_apply_edits_changes_only_editable_fields(unbuilt):
    p = plan.load(unbuilt)
    new = plan.apply_edits(p, {"modules": {"2": {"notes": "Changed."}}})
    assert new["modules"][1]["notes"] == "Changed."
    assert p["modules"][1]["notes"] == ""
    for field in ("tools", "teaches", "why"):
        with pytest.raises(PlanError, match=field):
            plan.apply_edits(p, {"modules": {"2": {field: []}}})


def test_apply_edits_mistakes_and_notes(built):
    p = plan.load(built)
    rows = [{"did": "Subtracted", "ask": "Which way?"}]
    new = plan.apply_edits(p, {"notes": "Hi", "modules": {"1": {"mistakes": {"double": rows}}}})
    assert new["notes"] == "Hi"
    assert _tool(new, "double")["mistakes"] == rows


def test_apply_edits_unknown_module(unbuilt):
    with pytest.raises(PlanError, match="9"):
        plan.apply_edits(plan.load(unbuilt), {"modules": {"9": {"notes": "x"}}})


def test_objectives_are_edited_in_the_intros(built):
    with pytest.raises(PlanError, match="module-intros.md"):
        plan.apply_edits(plan.load(built), {"modules": {"1": {"objectives": ["x"]}}})


def test_intro_status(built):
    p = plan.load(built)
    assert p["intro_status"] == "open"
    assert plan.apply_edits(p, {"intro_status": "reviewed"})["intro_status"] == "reviewed"
    with pytest.raises(PlanError, match="Introduction"):
        plan.apply_edits(p, {"intro_status": "done"})


def test_stop_is_1_or_2(built):
    data = json.loads((built / "review.json").read_text())
    data["stop"] = 3
    (built / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match="1 or 2"):
        plan.load(built)


def test_save_then_load(unbuilt):
    p = plan.apply_edits(plan.load(unbuilt), {"modules": {"1": {"status": "reviewed"}}})
    plan.save(unbuilt, p)
    assert plan.load(unbuilt)["modules"][0]["status"] == "reviewed"
    assert not list(unbuilt.glob("*.part"))


def test_code_blocks_slice_lines(built):
    data = plan.page_data(built, built)
    block = _tool(data, "double")["blocks"][0]
    lines = (built / "topic.py").read_text().splitlines()
    assert block == {"code": "\n".join(lines[2:5]), "note": "The tool itself.", "missing": False}


def test_code_block_past_end_is_marked(built):
    data = plan.page_data(built, built)
    assert _tool(data, "double")["blocks"][1]["missing"] is True
    assert _tool(data, "double")["blocks"][1]["code"] == ""
    assert _tool(data, "ghost")["blocks"][0]["missing"] is True


def test_page_data_unbuilt(unbuilt):
    data = plan.page_data(unbuilt, unbuilt)
    assert data["intros"] is None and data["has_tutor"] is False and data["eval"] is None


def test_page_data_built_has_intros(built):
    data = plan.page_data(built, built)
    assert data["has_tutor"] is True
    assert data["intros"]["modules"][0]["objectives"] == ["State the first idea.", "Use the first idea."]


def test_eval_summary(built):
    results = built / "evals" / "results"
    results.mkdir(parents=True)
    (results / "20250101-000000-built.json").write_text(json.dumps(
        {"a": {"checks": {"x": True, "y": True, "z": True}}, "b": {"checks": {"x": True, "y": True, "z": False}}}))
    (results / "20240101-000000-built.json").write_text(json.dumps({"a": {"checks": {"x": False}}}))
    (results / "20260101-000000-other.json").write_text(json.dumps({"a": {"checks": {"x": False}}}))
    ev = plan.page_data(built, built)["eval"]
    assert ev == {"file": "20250101-000000-built.json", "passed": 5, "total": 6}


def test_version_changes_with_either_file(built):
    v0 = plan.version(built)
    (built / "content" / "module-intros.md").write_text("changed")
    v1 = plan.version(built)
    (built / "review.json").write_text((built / "review.json").read_text() + " ")
    assert len({v0, v1, plan.version(built)}) == 3


def test_modules_must_be_a_list(unbuilt):
    data = json.loads((unbuilt / "review.json").read_text())
    data["modules"] = {"1": data["modules"][0]}
    (unbuilt / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match="modules"):
        plan.load(unbuilt)


def test_code_blocks_must_be_objects(built):
    data = json.loads((built / "review.json").read_text())
    data["modules"][0]["tools"][0]["code"] = ["3-5"]
    (built / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match="code"):
        plan.load(built)


def test_module_number_must_be_an_int(unbuilt):
    data = json.loads((unbuilt / "review.json").read_text())
    data["modules"][0]["n"] = "1"
    (unbuilt / "review.json").write_text(json.dumps(data))
    with pytest.raises(PlanError, match='"n"'):
        plan.load(unbuilt)


def test_load_fills_the_scope(unbuilt):
    scope = plan.load(unbuilt)["overview"]["scope"]
    assert scope == {"teaches": "", "nearby": "", "elsewhere": ""}
