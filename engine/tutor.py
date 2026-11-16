"""The tutoring agent: system prompt, the tool loop, and per-student storage.

One Tutor serves every student.  Each student is a JSON file in DATA_DIR,
named from their account key (acct-<id>, see auth.py), holding their record (which carries over
between sessions) and the current conversation (the API message history plus
what the browser shows).
"""

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from speech_text import SpeechStream
import intros
import settings
import tutor_config as cfg
from tools import TOOLS, ToolError, run_tool

MODEL = os.environ.get("TUTOR_MODEL", "claude-sonnet-5-5")
EFFORT = os.environ.get("TUTOR_EFFORT", "medium")
MAX_STEPS = 12  # model calls per student message; a turn normally needs 1-3


SESSION_START = ("[Session start. This note is from the app, not the student. "
                 "Open the session as the protocol says.]")


TEACHER_HEAD = ("# The teacher's instructions\n\n"
                "These come from the instructor who teaches this course. Follow them. Where one "
                "conflicts with the teaching protocol or a teaching script above, the teacher's "
                "instruction wins. The whiteboard and voice rules that follow still hold.\n\n")


def build_system_prompt(voice=False):
    """The shared teaching protocol, the tutor's topic section, its teaching
    scripts as references, the learning objectives, and (voice) the whiteboard
    rules."""
    parts = [(cfg.INSTRUCTIONS / "teaching.md").read_text(encoding="utf-8"),
             (cfg.CONTENT / "topic.md").read_text(encoding="utf-8")]
    for name in cfg.REFERENCES:
        text = (cfg.CONTENT / name).read_text(encoding="utf-8")
        parts.append(f"<reference file=\"{name}\">\n{text}\n</reference>")
    parts.append(intros.prompt_text())
    teacher = cfg.CONTENT / "teacher.md"
    if teacher.exists() and teacher.read_text().strip():
        parts.append(TEACHER_HEAD + teacher.read_text().strip())
    if voice:
        parts.append((cfg.INSTRUCTIONS / "voice.md").read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def record_text(progress):
    """The student record as it appears in the system prompt."""
    if not progress:
        return "Student record: none. This is the student's first session."
    lines = ["Student record from earlier sessions:"]
    if progress.get("modules_done"):
        lines.append("Modules done: " + ", ".join(str(m) for m in progress["modules_done"]))
    if progress.get("now_in"):
        lines.append("Now in: " + progress["now_in"])
    if progress.get("objectives_met"):
        lines.append("Objectives met: " + ", ".join(str(o) for o in progress["objectives_met"]))
    if progress.get("mistakes_seen"):
        lines.append("Mistakes seen: " + "; ".join(progress["mistakes_seen"]))
    if progress.get("notes"):
        lines.append("Notes: " + progress["notes"])
    return "\n".join(lines)


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s[:60]


def student_slug(name):
    """File name for a student.  An email address gets a hash of the whole
    address, so 'j.doe@' and 'j-doe@' never share a file."""
    name = name.strip().lower()
    if "@" not in name:
        return slugify(name)
    local = slugify(name.rpartition("@")[0])
    return f"{local}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.locks = {}

    def lock(self, slug):
        return self.locks.setdefault(slug, asyncio.Lock())

    def path(self, slug):
        return self.dir / f"{slug}.json"

    def load(self, key, name=None):
        """The record for key (acct-<id> for a signed-in student).  name is the
        name to show, kept up to date when a student changes their username."""
        slug = student_slug(key)
        if not slug:
            raise ValueError("empty name")
        name = (name or key).strip()
        p = self.path(slug)
        if p.exists():
            student = json.loads(p.read_text(encoding="utf-8"))
            student["name"] = name
            return student
        return {"name": name, "slug": slug, "progress": None,
                "conversation": None, "past_sessions": 0, "created": now()}

    def save(self, student):
        p = self.path(student["slug"])
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(student, indent=1), encoding="utf-8")
        tmp.replace(p)


def new_conversation(student, voice=False):
    # The record is frozen into the conversation when it starts, so the system
    # prompt never changes mid-conversation (that would break the prompt cache
    # and invalidate earlier thinking blocks).
    conv = {"started": now(), "record": record_text(student.get("progress")),
            "messages": [], "display": [], "trees": {}}
    if voice:
        conv["spoken"] = []
    return conv


class Tutor:
    def __init__(self, store, client=None, voice=False):
        self.store = store
        self.client = client or anthropic.AsyncAnthropic()
        self.voice = voice
        self.system_prompt = build_system_prompt(voice)

    def ensure_conversation(self, student, fresh=False):
        if fresh and student.get("conversation") and student["conversation"]["messages"]:
            student["past_sessions"] = student.get("past_sessions", 0) + 1
            student["conversation"] = None
        if not student.get("conversation"):
            student["conversation"] = new_conversation(student, self.voice)
        if self.voice:
            student["conversation"].setdefault("spoken", [])
        return student["conversation"]

    def _say(self, conv, sentences):
        events = []
        for sentence in sentences:
            conv["spoken"].append(sentence)
            events.append({"type": "say", "n": len(conv["spoken"]) - 1})
        return events

    def _intro(self, conv, n):
        """Events that play Module n's fixed intro, recorded in the display.
        'break' ends the tutor message in progress, so the intro stands alone."""
        md = intros.markdown(n)
        conv["display"].append({"role": "tutor", "text": md, "intro": True})
        events = [{"type": "break"}, {"type": "text", "text": md}, {"type": "break"}]
        if self.voice:
            speech = SpeechStream()
            events += self._say(conv, speech.feed(md) + speech.flush())
        return events

    async def start_turn(self, student):
        """The session-start turn. In the voice version, a new student's first
        session opens with the app's fixed Introduction, then the tutor asks its
        opening questions; otherwise the tutor opens as the protocol says."""
        conv = self.ensure_conversation(student)
        first = (self.voice and intros.COURSE and not student.get("progress")
                 and not student.get("past_sessions") and not conv["messages"])
        if not first:
            async for e in self.turn(student, SESSION_START, hidden=True):
                yield e
            return
        md = intros.course_markdown()
        conv["display"].append({"role": "tutor", "text": md, "intro": True})
        for e in [{"type": "break"}, {"type": "text", "text": md}, {"type": "break"}]:
            yield e
        speech = SpeechStream()
        for e in self._say(conv, speech.feed(md) + speech.flush()):
            yield e
        note = SESSION_START[:-1] + " " + intros.COURSE_NOTE + "]"
        async for e in self.turn(student, note, hidden=True):
            yield e

    async def module_turn(self, student, n):
        """The student picked Module n from the menu: play its intro, then let
        the tutor begin teaching it."""
        if n not in intros.MODULES:
            yield {"type": "error", "message": "There is no such module."}
            return
        conv = self.ensure_conversation(student)
        conv["display"].append({"role": "student",
                                "text": f"Take me to Module {n}: {intros.MODULES[n]['title']}."})
        for e in self._intro(conv, n):
            yield e
        note = ("[This note is from the app, not the student. The student picked Module "
                f"{n} from the menu.] " + intros.note(n))
        async for e in self.turn(student, note, hidden=True):
            yield e

    async def turn(self, student, user_text, hidden=False):
        """Run one student message through the tool loop.

        Yields browser events: {'type': 'text', 'text': delta},
        {'type': 'tree', 'tree': payload}, {'type': 'error', 'message': str},
        and {'type': 'break'}, which ends the tutor message in progress (around
        a module intro).
        With voice on, also {'type': 'say', 'n': i}, where i indexes
        conv['spoken'].
        Saves the student when done, including on error.
        """
        conv = self.ensure_conversation(student)
        msgs = conv["messages"]
        msgs.append({"role": "user", "content": user_text})
        if not hidden:
            conv["display"].append({"role": "student", "text": user_text})
        state = {"trees": conv["trees"], "progress": student.get("progress")}
        buf = []
        speech = SpeechStream() if self.voice else None

        def say(sentences):
            return self._say(conv, sentences)

        def flush():
            if "".join(buf).strip():
                conv["display"].append({"role": "tutor", "text": "".join(buf)})
            buf.clear()

        if settings.TEACHER:          # the preview: the teacher's edits apply at the next turn
            self.system_prompt = build_system_prompt(self.voice)
        system = [{"type": "text", "text": self.system_prompt},
                  {"type": "text", "text": conv["record"]}]
        try:
            for _ in range(MAX_STEPS):
                async with self.client.beta.messages.stream(
                    model=MODEL,
                    max_tokens=16000,
                    system=system,
                    tools=TOOLS,
                    messages=msgs,
                    output_config={"effort": EFFORT},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            buf.append(event.text)
                            yield {"type": "text", "text": event.text}
                            if speech:
                                for e in say(speech.feed(event.text)):
                                    yield e
                    response = await stream.get_final_message()

                # Echo every block back unchanged (thinking blocks included).
                msgs.append({"role": "assistant",
                             "content": [b.to_dict() for b in response.content]})

                if response.stop_reason == "refusal":
                    yield {"type": "error", "message": "The tutor could not answer that. Try rephrasing."}
                    break
                if response.stop_reason == "pause_turn":
                    continue
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                if not tool_uses:
                    if speech:
                        for e in say(speech.flush()):
                            yield e
                    break
                if response.stop_reason == "max_tokens":
                    yield {"type": "error", "message": "The reply was cut off. Please ask again."}
                    break

                results = []
                for b in tool_uses:
                    try:
                        text, payload = run_tool(b.name, b.input, state)
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": text})
                        if payload:
                            if speech:
                                for e in say(speech.flush()):
                                    yield e
                            flush()
                            if "intro" in payload:
                                for e in self._intro(conv, payload["intro"]):
                                    yield e
                            elif "plot" in payload:
                                conv["display"].append({"role": "plot", "plot": payload["plot"]})
                                yield {"type": "plot", "plot": payload["plot"]}
                            else:
                                conv["display"].append({"role": "tree", "tree": payload})
                                yield {"type": "tree", "tree": payload}
                    except (ToolError, KeyError, TypeError, ValueError) as e:
                        results.append({"type": "tool_result", "tool_use_id": b.id,
                                        "content": f"Error: {e}", "is_error": True})
                msgs.append({"role": "user", "content": results})
                if buf and not "".join(buf).endswith("\n"):
                    buf.append("\n\n")
                    yield {"type": "text", "text": "\n\n"}
                    if speech:   # the separator ends the sentence in progress
                        for e in say(speech.feed("\n\n")):
                            yield e
            else:
                yield {"type": "error", "message": "The tutor took too many steps. Please ask again."}
        except anthropic.RateLimitError:
            yield {"type": "error", "message": "The tutor is busy. Wait a moment and try again."}
        except anthropic.APIConnectionError:
            yield {"type": "error", "message": "Could not reach the tutor service. Check the connection."}
        except anthropic.APIStatusError as e:
            yield {"type": "error", "message": f"Tutor service error ({e.status_code}). Please try again."}
        finally:
            flush()
            # A failed call can leave a dangling user turn; drop back to a
            # clean history so the next message is valid.
            _repair(msgs)
            student["progress"] = state["progress"]
            conv["updated"] = now()
            self.store.save(student)


def _repair(msgs):
    """Make the history end on a complete assistant turn.

    Removes trailing user messages that never got a reply and assistant turns
    whose tool calls were never answered, so the next request does not start
    with two user turns or carry a tool_use without its result.  Only the tail
    is cut; earlier turns are never edited.
    """
    while msgs:
        last = msgs[-1]
        if last["role"] == "user":
            msgs.pop()
        elif any(isinstance(b, dict) and b.get("type") == "tool_use" for b in last["content"]):
            msgs.pop()
        else:
            break
