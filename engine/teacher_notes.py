"""The teacher's notes from the preview (scripts/preview.sh, /tutor:edit).

While the teacher plays the tutor on their own computer, the board has a Note
button. Each note is one line of <tutor>/notes.jsonl, with where the teacher
was when they wrote it:

    {"id": 3, "time": "...", "text": "...", "module": 2, "section": "Discount each one",
     "tutor_said": "...", "status": "new", "reply": ""}

Claude Code applies each new note to the tutor's files and sets its status to
"applied" (or "question", with a reply, when it needs the teacher to say more).
The board shows the notes and their status.  Students never see any of this:
the routes exist only when the preview runs (TUTORS_TEACHER=1 with
TUTORS_LOCAL=1)."""

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_NOTE = 4000
MAX_CONTEXT = 1500
_lock = threading.Lock()


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def where(display: list[dict]) -> dict:
    """The module, the board section and the tutor's last words, from the
    conversation's display."""
    module, section, said = None, None, ""
    for d in display:
        if d.get("role") != "tutor":
            continue
        text = d.get("text", "")
        for m in re.finditer(r"^## (.+)$", text, re.M):
            title = m.group(1).strip()
            mod = re.match(r"Module (\d+)\b", title)
            if mod:
                module = int(mod.group(1))
            else:
                section = title
        if text.strip():
            said = text
    return {"module": module, "section": section, "tutor_said": said.strip()[-MAX_CONTEXT:]}


def add(path: Path, text: str, display: list[dict]) -> dict:
    text = text.strip()[:MAX_NOTE]
    with _lock:
        notes = load(path)
        note = {"id": max((n.get("id", 0) for n in notes), default=0) + 1,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "text": text, **where(display), "status": "new", "reply": ""}
        with path.open("a") as f:
            f.write(json.dumps(note) + "\n")
    return note
