"""Read and write a tutor's content/module-intros.md, for the review page.

The format is the one engine/intros.py reads: a preamble, then "## Introduction"
and "## Module N — Title" sections with "Spoken:", "Board:" and "Objectives:"
parts.  This module does not import the engine, because a tutor being built may
have no tutor.toml or topic.py yet.
"""

import re
import textwrap
from pathlib import Path

_PARTS = re.compile(r"^(Spoken|Board|Objectives):\n(.*?)(?=^\w+:\n|\Z)", re.M | re.S)
_MODULE = re.compile(r"Module\s+(\d+)\s*[—–-]\s*(.+)")


def _items(s):
    return [ln[2:].strip() for ln in s.splitlines() if ln.startswith("- ")]


def read(path: Path) -> dict:
    """{"preamble", "course": {"spoken", "board"} or None, "modules": [{"n", "title", "spoken", "board", "objectives"}]}."""
    text = Path(path).read_text(encoding="utf-8")
    first = re.search(r"^## ", text, re.M)
    preamble = text[:first.start()] if first else text
    course, modules = None, []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        parts = dict(_PARTS.findall(body))
        spoken = " ".join(parts.get("Spoken", "").split())
        if head.strip() == "Introduction":
            course = {"spoken": spoken, "board": _items(parts.get("Board", ""))}
            continue
        m = _MODULE.match(head)
        if m:
            modules.append({"n": int(m.group(1)), "title": m.group(2).strip(), "spoken": spoken,
                            "board": _items(parts.get("Board", "")),
                            "objectives": _items(parts.get("Objectives", ""))})
    modules.sort(key=lambda m: m["n"])
    return {"preamble": preamble, "course": course, "modules": modules}


_HEADER = re.compile(r"^\w+:$")


def _wrap(text):
    """The spoken paragraph in lines of at most 79 columns, except that no line
    may look like a part header ("follows:"): the engine would end the
    paragraph there.  Such a line joins the line before it."""
    lines = textwrap.wrap(" ".join(text.split()), 79)
    out = []
    for line in lines:
        if out and _HEADER.match(line):
            out[-1] += " " + line
        else:
            out.append(line)
    return "\n".join(out)


def _section(head, spoken, board, objectives=None):
    out = [f"## {head}", "", "Spoken:", _wrap(spoken), "", "Board:"]
    out += [f"- {b}" for b in board]
    if objectives is not None:
        out += ["", "Objectives:"] + [f"- {o}" for o in objectives]
    return "\n".join(out) + "\n"


def write(path: Path, doc: dict) -> None:
    """Write doc (the shape read() returns) back to path."""
    sections = []
    if doc.get("course"):
        sections.append(_section("Introduction", doc["course"]["spoken"], doc["course"]["board"]))
    for m in sorted(doc["modules"], key=lambda m: m["n"]):
        sections.append(_section(f"Module {m['n']} — {m['title']}", m["spoken"], m["board"], m["objectives"]))
    path = Path(path)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(doc.get("preamble", "") + "\n".join(sections), encoding="utf-8")
    tmp.replace(path)
