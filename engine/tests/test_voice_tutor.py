import asyncio
import hashlib
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
from tutor import Store, Tutor, build_system_prompt  # noqa: E402

TREE = {"S": 100, "K": 100, "r": 0.02, "u": 1.1, "d": 0.9, "n": 2, "kind": "European call"}


class Block(SimpleNamespace):
    def to_dict(self):
        return dict(vars(self))


def text_block(t):
    return Block(type="text", text=t)


def tool_block(name, inp, id="tu1"):
    return Block(type="tool_use", name=name, input=inp, id=id)


class FakeStream:
    def __init__(self, texts, blocks, stop):
        self.texts, self.blocks, self.stop = texts, blocks, stop

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self._events()

    async def _events(self):
        for t in self.texts:
            yield SimpleNamespace(type="text", text=t)

    async def get_final_message(self):
        return SimpleNamespace(content=self.blocks, stop_reason=self.stop)


class FakeClient:
    """Each script step is (text deltas, extra blocks, stop_reason)."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        texts, extra, stop = self.steps.pop(0)
        return FakeStream(texts, [text_block("".join(texts))] + extra, stop)


def student():
    return {"name": "Ann", "slug": "ann", "progress": None, "conversation": None,
            "past_sessions": 0}


def run_turn(tmp_path, steps, voice):
    tutor = Tutor(Store(tmp_path), client=FakeClient(steps), voice=voice)
    s = student()

    async def go():
        return [e async for e in tutor.turn(s, "hi")]

    return asyncio.run(go()), s


REPLY = ["Good start. Here is q.\n\n", "$$q=0.6$$", "\n\nWhat next?"]


# SHA-256 of build_system_prompt() at the baseline commit 6e0465e (before voice work).
def test_voice_prompt_adds_the_whiteboard_rules():
    p = build_system_prompt()
    assert "# Voice mode" not in p and "Voice mode" in build_system_prompt(voice=True)


def test_voice_prompt_appends_voice_rules_last():
    p = build_system_prompt(voice=True)
    assert p.startswith(build_system_prompt()) and "overrides" in p and "$$" in p


def test_voice_turn_yields_say_events_in_order(tmp_path):
    evs, s = run_turn(tmp_path, [(REPLY, [], "end_turn")], voice=True)
    assert [e["n"] for e in evs if e["type"] == "say"] == [0, 1, 2]
    assert s["conversation"]["spoken"] == ["Good start.", "Here is q.", "What next?"]
    assert [e for e in evs if e["type"] == "text"]


def test_text_tutor_yields_no_say_events(tmp_path):
    evs, s = run_turn(tmp_path, [(REPLY, [], "end_turn")], voice=False)
    assert not [e for e in evs if e["type"] == "say"]
    assert "spoken" not in s["conversation"]


def test_old_conversation_gets_spoken_key(tmp_path):
    tutor = Tutor(Store(tmp_path), client=FakeClient([(REPLY, [], "end_turn")]), voice=True)
    s = student()
    s["conversation"] = {"started": "x", "record": "r", "messages": [], "display": [], "trees": {}}

    async def go():
        return [e async for e in tutor.turn(s, "hi")]

    asyncio.run(go())
    assert len(s["conversation"]["spoken"]) == 3


def test_tree_flushes_pending_speech_first(tmp_path):
    steps = [(["Here is the tree"], [tool_block("show_tree", TREE)], "tool_use"),
             (["Find the root."], [], "end_turn")]
    evs, s = run_turn(tmp_path, steps, voice=True)
    kinds = [e["type"] for e in evs if e["type"] in ("say", "tree")]
    assert kinds == ["say", "tree", "say"]
    assert s["conversation"]["spoken"] == ["Here is the tree", "Find the root."]


def test_error_drops_unflushed_speech(tmp_path):
    evs, s = run_turn(tmp_path, [(["Half a sent"], [], "refusal")], voice=True)
    assert not [e for e in evs if e["type"] == "say"]
    assert s["conversation"]["spoken"] == []


def test_step_separator_ends_the_spoken_sentence(tmp_path, monkeypatch):
    import tutor as tutor_mod
    monkeypatch.setattr(tutor_mod, "run_tool", lambda name, inp, state: ("ok", None))   # no tree payload
    steps = [(["Let me check your answer."], [tool_block("check_answer", {})], "tool_use"),
             (["That is right. Now find q."], [], "end_turn")]
    evs, s = run_turn(tmp_path, steps, voice=True)
    assert s["conversation"]["spoken"] == ["Let me check your answer.", "That is right.", "Now find q."]
    kinds = [e["type"] if e["type"] != "text" else repr(e["text"]) for e in evs]
    # The first sentence is said before the second model call's text arrives.
    assert kinds.index("say") < kinds.index(repr("That is right. Now find q."))


def test_the_teacher_file_goes_into_the_prompt_before_the_voice_rules(monkeypatch, tmp_path):
    import tutor_config as cfg
    import shutil
    content = tmp_path / "content"
    shutil.copytree(cfg.CONTENT, content)
    monkeypatch.setattr(cfg, "CONTENT", content)
    base = build_system_prompt(voice=True)
    assert "The teacher's instructions" not in base
    (content / "teacher.md").write_text("Give an analogy before every formula.\n")
    p = build_system_prompt(voice=True)
    i, v = p.index("Give an analogy before every formula."), p.index("# Voice mode")
    assert p.index("# The teacher's instructions") < i < v
