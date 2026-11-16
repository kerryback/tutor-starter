#!/usr/bin/env python3
"""The teacher's notes from the preview (engine/teacher_notes.py), for Claude Code.

    scripts/notes.py wait capm            wait for a new note; print the new notes and exit
    scripts/notes.py list capm            print every note
    scripts/notes.py set capm 3 applied "Added the analogy to 02-tangency.md, part 3."
    scripts/notes.py set capm 4 question "Which example should the analogy replace?"

Run `wait` in the background: it exits as soon as the teacher saves a note.
The board shows each note's status and reply."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import teacher_notes  # noqa: E402

STATUSES = ("new", "applied", "question", "skipped")


def path(tutor):
    d = ROOT / tutor
    if not (d / "tutor.toml").exists():
        sys.exit(f"No tutor named {tutor!r}.")
    return d / "notes.jsonl"


def main(argv):
    if len(argv) < 2 or argv[0] not in ("wait", "list", "set"):
        sys.exit(__doc__)
    cmd, p = argv[0], path(argv[1])
    if cmd == "list":
        for n in teacher_notes.load(p):
            print(json.dumps(n))
    elif cmd == "wait":
        while True:
            new = [n for n in teacher_notes.load(p) if n.get("status") == "new"]
            if new:
                for n in new:
                    print(json.dumps(n, indent=1))
                return
            time.sleep(2)
    else:
        if len(argv) < 4 or argv[3] not in STATUSES:
            sys.exit("set <tutor> <id> <" + "|".join(STATUSES) + "> [reply]")
        nid, status, reply = int(argv[2]), argv[3], " ".join(argv[4:])
        with teacher_notes._lock:
            notes = teacher_notes.load(p)
            if not any(n.get("id") == nid for n in notes):
                sys.exit(f"No note {nid}.")
            for n in notes:
                if n.get("id") == nid:
                    n["status"], n["reply"] = status, reply
            p.write_text("".join(json.dumps(n) + "\n" for n in notes))
        print(f"Note {nid}: {status}")


if __name__ == "__main__":
    main(sys.argv[1:])
