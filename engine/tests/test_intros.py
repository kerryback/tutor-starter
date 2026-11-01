import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import intros  # noqa: E402
from speech_text import SpeechStream  # noqa: E402
from test_voice_tutor import FakeClient, student, tool_block  # noqa: E402
from tools import ToolError, calculate, run_tool  # noqa: E402
from tutor import Store, Tutor, build_system_prompt  # noqa: E402


def test_four_modules_with_intros_and_objectives():
    assert sorted(intros.MODULES) == [1, 2, 3, 4]
    assert [len(m["objectives"]) for m in intros.MODULES.values()] == [4, 4, 8, 4]
    for m in intros.MODULES.values():
        assert m["title"] and len(m["board"]) == 3 and len(m["spoken"].split()) > 40
    every = " ".join(o for m in intros.MODULES.values() for o in m["objectives"])
    assert "does not affect the price" not in every and "between zero and one" not in every


def test_only_the_spoken_paragraph_is_spoken():
    md = intros.markdown(3)
    assert md.startswith("## Module 3: Many periods and calibration\n")
    s = SpeechStream()
    spoken = " ".join(s.feed(md) + s.flush())
    assert spoken == intros.MODULES[3]["spoken"]


def test_objectives_with_ids_are_in_the_prompt():
    p = build_system_prompt()
    assert "3.5 Extend the method to a tree with many periods." in p
    assert "start_module" in p and "Never compute a number yourself" in p


@pytest.mark.parametrize("expr,value", [
    ("0.6*110 + 0.4*90", "102"), ("(0.6*10 + 0.4*0)/1.02", "5.882352941"),
    ("max(110 - 100, 0)", "10"), ("(1.02 - 0.9)/(1.1 - 0.9)", "0.6"), ("1.1^2*100", "121"),
    ("100 × 1.1 − 5", "105"),
])
def test_calculate(expr, value):
    assert calculate(expr) == f"{expr} = {value}"


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "2**1000", "1/0", "x + 1", "(1"])
def test_calculate_refuses_anything_but_arithmetic(expr):
    with pytest.raises(ToolError):
        calculate(expr)


def test_start_module_tool():
    text, payload = run_tool("start_module", {"module": 2}, {"trees": {}, "progress": None})
    assert payload == {"intro": 2} and "Do not give an overview" in text and "2.4" in text
    with pytest.raises(ToolError):
        run_tool("start_module", {"module": 7}, {"trees": {}, "progress": None})


def test_save_progress_keeps_objectives_met():
    st = {"trees": {}, "progress": None}
    run_tool("save_progress", {"modules_done": [1], "now_in": "2", "mistakes_seen": [],
                               "objectives_met": ["1.1", "1.2"]}, st)
    assert st["progress"]["objectives_met"] == ["1.1", "1.2"]


def _events(gen):
    async def go():
        return [e async for e in gen]
    return asyncio.run(go())


def test_tutor_calling_start_module_plays_the_fixed_intro(tmp_path):
    steps = [([], [tool_block("start_module", {"module": 3})], "tool_use"),
             (["## Two periods\n\nLet's begin. What is the stock worth after two up moves?"], [], "end_turn")]
    tutor = Tutor(Store(tmp_path), client=FakeClient(steps), voice=True)
    s = student()
    evs = _events(tutor.turn(s, "next module please"))
    i = evs.index({"type": "text", "text": intros.markdown(3)})
    assert evs[i - 1] == {"type": "break"} and evs[i + 1] == {"type": "break"}
    spoken = s["conversation"]["spoken"]
    assert " ".join(spoken[:-2]) == intros.MODULES[3]["spoken"]
    assert spoken[-1] == "What is the stock worth after two up moves?"
    texts = [d["text"] for d in s["conversation"]["display"] if d["role"] == "tutor"]
    assert texts[0] == intros.markdown(3) and texts[1].startswith("## Two periods")
    result = s["conversation"]["messages"][2]["content"][0]
    assert result["type"] == "tool_result" and "Do not give an overview" in result["content"]


def test_menu_choice_plays_the_intro_then_the_tutor_teaches(tmp_path):
    steps = [(["## Finding q\n\nLook at the stock prices on the board. What q fits them?"], [], "end_turn")]
    tutor = Tutor(Store(tmp_path), client=FakeClient(steps), voice=True)
    s = student()
    evs = _events(tutor.module_turn(s, 2))
    assert evs[:2] == [{"type": "break"}, {"type": "text", "text": intros.markdown(2)}]
    disp = s["conversation"]["display"]
    assert disp[0] == {"role": "student", "text": "Take me to Module 2: Risk-neutral probabilities."}
    assert disp[1]["text"] == intros.markdown(2) and disp[2]["text"].startswith("## Finding q")
    note = s["conversation"]["messages"][0]["content"]
    assert "picked Module 2" in note and "not the student" in note
    assert not [d for d in disp if d.get("text", "").startswith("[This note")]   # the note stays hidden


def test_menu_choice_of_a_missing_module_is_an_error(tmp_path):
    tutor = Tutor(Store(tmp_path), client=FakeClient([]), voice=True)
    evs = _events(tutor.module_turn(student(), 9))
    assert evs == [{"type": "error", "message": "There is no such module."}]


def test_text_version_shows_the_intro_without_speech(tmp_path):
    steps = [(["Let's begin."], [], "end_turn")]
    tutor = Tutor(Store(tmp_path), client=FakeClient(steps), voice=False)
    s = student()
    evs = _events(tutor.module_turn(s, 1))
    assert not [e for e in evs if e["type"] == "say"]
    assert {"type": "text", "text": intros.markdown(1)} in evs
    json.dumps(s)   # the record stays saveable


def _start(tmp_path, s, voice):
    steps = [(["## Getting started\n\nWhat would you like to cover?"], [], "end_turn")]
    tutor = Tutor(Store(tmp_path), client=FakeClient(steps), voice=voice)
    return _events(tutor.start_turn(s)), s


def test_new_voice_student_gets_the_fixed_introduction_first(tmp_path):
    evs, s = _start(tmp_path, student(), voice=True)
    assert evs[:2] == [{"type": "break"}, {"type": "text", "text": intros.course_markdown()}]
    disp = s["conversation"]["display"]
    assert disp[0]["text"].startswith("## Introduction\n") and disp[1]["text"].startswith("## Getting started")
    spoken = s["conversation"]["spoken"]
    assert spoken[0] == "Welcome to the binomial tutor." and spoken[-1] == "What would you like to cover?"
    assert intros.MIC_NOTE in spoken      # the microphone sentence ends the Introduction
    assert intros.course_markdown().index(intros.ARITHMETIC_NOTE) < intros.course_markdown().index(intros.MIC_NOTE)
    note = s["conversation"]["messages"][0]["content"]
    assert note.startswith("[Session start.") and "Do not repeat any of it" in note
    assert not [d for d in disp if d["role"] == "student"]     # the note stays hidden


def test_returning_student_and_text_version_get_no_introduction(tmp_path):
    back = student(); back["progress"] = {"modules_done": [1], "now_in": "2", "mistakes_seen": []}
    evs, s = _start(tmp_path / "a", back, voice=True)
    assert not [d for d in s["conversation"]["display"] if d.get("text", "").startswith("## Introduction")]
    evs, s = _start(tmp_path / "b", student(), voice=False)
    assert not [d for d in s["conversation"]["display"] if d.get("text", "").startswith("## Introduction")]
    assert "Do not repeat" not in s["conversation"]["messages"][0]["content"]


def test_introduction_lists_every_module():
    md = intros.course_markdown()
    for n, m in intros.MODULES.items():
        assert f"- Module {n}: {m['title']}" in md
