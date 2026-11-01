"""A tutor's review.json: the plan the tutor skill writes, and the edits the
review page saves.  The format is in skill/tutor/references/review-json.md.
"""

import copy
import hashlib
import json
from pathlib import Path

from review import intros_file


class PlanError(ValueError):
    """A problem with review.json or an edit, said in one plain sentence."""


_DEFAULTS = {"overview": dict, "notes": str, "intro_status": lambda: "open"}
_OVERVIEW = {"summary": str, "sources": list, "data": list, "packages": list, "left_out": list,
             "scope": dict}
_SCOPE = {"teaches": str, "nearby": str, "elsewhere": str}
_MODULE = {"examples": list, "concepts": list, "tools": list,
           "plots": list, "status": lambda: "open", "notes": str}
_CONCEPT = {"scripts": list}
_SCRIPT = {"computes": str, "script": str, "origin": lambda: "new"}
_TOOL = {"source": lambda: "new", "does": str, "inputs": str, "returns": str, "tests": str,
         "file": lambda: "topic.py", "code": list, "mistakes": list}
_PLOT = {"shows": str, "preview": lambda: None}

# Module fields the page may change.  "mistakes" is {tool name: rows}.
EDITABLE = {"examples", "mistakes", "status", "notes"}
STATUSES = ("open", "reviewed")


def _fill(obj, defaults):
    for key, make in defaults.items():
        obj.setdefault(key, make())


def _need(obj, keys, where):
    for key in keys:
        if key not in obj:
            raise PlanError(f"review.json is missing \"{key}\" {where}.")


def _list_of_objects(value, key, where):
    if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
        raise PlanError(f"review.json has \"{key}\" {where} as something other than a list of {{...}} entries.")


def load(tutor_dir: Path) -> dict:
    path = Path(tutor_dir) / "review.json"
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise PlanError(f"There is no review.json in {Path(tutor_dir).name}.") from None
    except json.JSONDecodeError as e:
        raise PlanError(f"review.json is not valid JSON at line {e.lineno}: {e.msg}.") from None
    if not isinstance(data, dict):
        raise PlanError("review.json must hold one JSON object.")
    _need(data, ("tutor", "title", "stop", "modules"), "at the top level")
    if data["stop"] not in (1, 2):
        raise PlanError("review.json has \"stop\" set to something other than 1 or 2.")
    _list_of_objects(data["modules"], "modules", "at the top level")
    _fill(data, _DEFAULTS)
    if not isinstance(data["overview"], dict):
        raise PlanError("review.json has \"overview\" as something other than one {...} entry.")
    _fill(data["overview"], _OVERVIEW)
    if not isinstance(data["overview"]["scope"], dict):
        raise PlanError("review.json has \"scope\" in the overview as something other than one {...} entry.")
    _fill(data["overview"]["scope"], _SCOPE)
    for i, m in enumerate(data["modules"], 1):
        _need(m, ("n", "title"), f"in module number {i} of the list")
        if not isinstance(m["n"], int) or isinstance(m["n"], bool):
            raise PlanError(f"review.json has \"n\" in module number {i} of the list as something other than a whole number.")
        _fill(m, _MODULE)
        for key in ("concepts", "tools", "plots", "examples"):
            _list_of_objects(m[key], key, f"in module {m['n']}")
        for c in m["concepts"]:
            _need(c, ("name",), f"in a concept of module {m['n']}")
            _fill(c, _CONCEPT)
            _list_of_objects(c["scripts"], "scripts", f"in the concept {c['name']}")
            for row in c["scripts"]:
                _fill(row, _SCRIPT)
        for t in m["tools"]:
            _need(t, ("name",), f"in a tool of module {m['n']}")
            _fill(t, _TOOL)
            for key in ("code", "mistakes"):
                _list_of_objects(t[key], key, f"in the tool {t['name']}")
        for p in m["plots"]:
            _need(p, ("name",), f"in a plot of module {m['n']}")
            _fill(p, _PLOT)
    return data


def version(tutor_dir: Path) -> str:
    h = hashlib.sha256()
    for name in ("review.json", "content/module-intros.md"):
        path = Path(tutor_dir) / name
        h.update(path.read_bytes() if path.exists() else b"")
        h.update(b"\0")
    return h.hexdigest()


def apply_edits(plan: dict, edits: dict) -> dict:
    new = copy.deepcopy(plan)
    if "notes" in edits:
        new["notes"] = str(edits["notes"])
    if "intro_status" in edits:
        if edits["intro_status"] not in STATUSES:
            raise PlanError("The Introduction's status must be open or reviewed.")
        new["intro_status"] = edits["intro_status"]
    modules = {str(m["n"]): m for m in new["modules"]}
    for n, fields in (edits.get("modules") or {}).items():
        if str(n) not in modules:
            raise PlanError(f"There is no module {n} in review.json.")
        m = modules[str(n)]
        for field, value in fields.items():
            if field == "objectives":
                raise PlanError("The objectives are in module-intros.md; edit them there.")
            if field not in EDITABLE:
                raise PlanError(f"The page cannot change \"{field}\"; ask Claude in the notes instead.")
            if field == "mistakes":
                tools = {t["name"]: t for t in m["tools"]}
                for name, rows in value.items():
                    if name not in tools:
                        raise PlanError(f"Module {n} has no tool named {name}.")
                    tools[name]["mistakes"] = rows
            else:
                m[field] = value
    return new


def save(tutor_dir: Path, plan: dict) -> None:
    path = Path(tutor_dir) / "review.json"
    tmp = path.with_name("review.json.part")
    tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _blocks(tutor_dir, tool):
    path = Path(tutor_dir) / tool["file"]
    lines = path.read_text().splitlines() if path.is_file() else None
    out = []
    for block in tool["code"]:
        start, _, end = str(block.get("lines", "")).partition("-")
        try:
            a, b = int(start), int(end or start)
        except ValueError:
            a, b = 0, -1
        ok = lines is not None and 1 <= a <= b <= len(lines)
        out.append({"code": "\n".join(lines[a - 1:b]) if ok else "", "note": block.get("note", ""),
                    "missing": not ok})
    return out


def _latest_eval(root, name):
    files = sorted((Path(root) / "evals" / "results").glob(f"*-{name}.json"))
    if not files:
        return None
    results = json.loads(files[-1].read_text())
    checks = [ok for scenario in results.values() for ok in scenario.get("checks", {}).values()]
    return {"file": files[-1].name, "passed": sum(bool(c) for c in checks), "total": len(checks)}


def page_data(tutor_dir: Path, root: Path) -> dict:
    tutor_dir = Path(tutor_dir)
    data = load(tutor_dir)
    for m in data["modules"]:
        for t in m["tools"]:
            t["blocks"] = _blocks(tutor_dir, t)
    intros = tutor_dir / "content" / "module-intros.md"
    data["intros"] = intros_file.read(intros) if intros.exists() else None
    data["version"] = version(tutor_dir)
    data["has_tutor"] = (tutor_dir / "tutor.toml").exists()
    data["eval"] = _latest_eval(root, tutor_dir.name)
    return data
