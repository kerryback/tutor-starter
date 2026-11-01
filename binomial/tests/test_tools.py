import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools import TOOLS, ToolError, run_tool  # noqa: E402
from tutor import _repair, build_system_prompt, record_text, slugify  # noqa: E402

TREE = {"S": 100, "K": 100, "r": 0.02, "u": 1.1, "d": 0.9, "n": 2, "kind": "European call"}


def state():
    return {"trees": {}, "progress": None}


def test_show_tree_never_sends_hidden_values():
    st = state()
    _, payload = run_tool("show_tree", {**TREE, "hide": "u"}, st)
    hidden = {nd["label"] for nd in payload["nodes"] if nd["V"] is None}
    assert hidden == {"0", "u"}
    # the payload as the browser receives it contains no value of a hidden node
    text = json.dumps(payload)
    key = run_tool("price_tree", TREE, st)[0]
    root_value = key.splitlines()[3].split()[2]   # "0  S  value ..."
    assert root_value[:4] not in text


def test_show_tree_all_and_none():
    st = state()
    _, p_all = run_tool("show_tree", {**TREE, "hide": "all"}, st)
    _, p_none = run_tool("show_tree", {**TREE, "hide": "none"}, st)
    assert all(nd["V"] is None for nd in p_all["nodes"])
    assert all(nd["V"] is not None for nd in p_none["nodes"])
    assert list(st["trees"]) == ["T1", "T2"]


def test_check_answer_against_shown_tree():
    st = state()
    run_tool("show_tree", {**TREE, "n": 1, "hide": "0"}, st)
    res = json.loads(run_tool("check_answer", {"tree_id": "T1", "node": "0", "answer": 4.90}, st)[0])
    assert res["correct"] is False and res["matches"][0]["mistake"] == "real_prob_half"
    res = json.loads(run_tool("check_answer", {"tree_id": "T1", "node": "0", "answer": 5.88}, st)[0])
    assert res["correct"] is True


def test_check_answer_unknown_tree():
    with pytest.raises(ToolError):
        run_tool("check_answer", {"tree_id": "T9", "node": "0", "answer": 1}, state())


def test_textbook_inputs():
    key = run_tool("price_tree", {"S": 100, "K": 100, "n": 4, "kind": "American put",
                                  "rate": 0.05, "sigma": 0.3, "T": 1}, state())[0]
    assert "q = 0.504342" in key


def test_arbitrage_and_bad_input_are_tool_errors():
    with pytest.raises(ToolError, match="No-arbitrage"):
        run_tool("price_tree", {**TREE, "r": 0.2}, state())
    with pytest.raises(ToolError):
        run_tool("price_tree", {"S": 100, "K": 100, "n": 2, "kind": "call"}, state())
    with pytest.raises(ToolError):
        run_tool("show_tree", {**TREE, "hide": "uuu"}, state())


def test_save_progress():
    st = state()
    run_tool("save_progress", {"modules_done": [1], "now_in": "2", "mistakes_seen": ["no discount"]}, st)
    assert "Modules done: 1" in record_text(st["progress"])


def test_tool_schemas_are_valid():
    for t in TOOLS:
        for req in t["input_schema"]["required"]:
            assert req in t["input_schema"]["properties"]


def test_system_prompt_has_everything():
    p = build_system_prompt()
    for marker in ["The one rule that matters most", "01-replication.md", "04-american.md", "Problem bank"]:
        assert marker in p


def test_repair_cuts_only_the_tail():
    ok = [{"role": "user", "content": "hi"},
          {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}]
    msgs = ok + [{"role": "user", "content": "q"},
                 {"role": "assistant", "content": [{"type": "tool_use", "id": "x", "name": "n", "input": {}}]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "r"}]}]
    _repair(msgs)
    assert msgs == ok
    _repair(msgs)
    assert msgs == ok


def test_slugify():
    assert slugify("  Ada Lovelace ") == "ada-lovelace" and slugify("!!!") == ""
