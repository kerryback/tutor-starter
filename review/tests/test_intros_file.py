from pathlib import Path

import intros

from review import intros_file

ROOT = Path(__file__).parents[2]
BINOMIAL = ROOT / "binomial" / "content" / "module-intros.md"


def test_reads_binomial_like_the_engine():
    doc = intros_file.read(BINOMIAL)
    engine = intros.load(BINOMIAL)
    assert [m["n"] for m in doc["modules"]] == sorted(engine)
    for m in doc["modules"]:
        for key in ("title", "spoken", "board", "objectives"):
            assert m[key] == engine[m["n"]][key]
    assert doc["course"] == intros.load_course(BINOMIAL)


def test_write_then_read_is_identity(tmp_path):
    doc = intros_file.read(BINOMIAL)
    out = tmp_path / "module-intros.md"
    intros_file.write(out, doc)
    assert intros_file.read(out) == doc


def test_write_keeps_the_preamble(tmp_path):
    out = tmp_path / "module-intros.md"
    intros_file.write(out, intros_file.read(BINOMIAL))
    original = BINOMIAL.read_text()
    preamble = original[:original.index("\n## ") + 1]
    assert out.read_text().startswith(preamble)


def test_spoken_lines_fit(tmp_path):
    out = tmp_path / "module-intros.md"
    intros_file.write(out, intros_file.read(BINOMIAL))
    lines = out.read_text().splitlines()
    spoken = []
    for i, line in enumerate(lines):
        if line == "Spoken:":
            j = i + 1
            while j < len(lines) and lines[j]:
                spoken.append(lines[j]); j += 1
    assert spoken and max(len(s) for s in spoken) <= 79


def test_spoken_text_ending_in_a_colon_survives(tmp_path):
    doc = intros_file.read(BINOMIAL)
    for width in range(30, 90):   # whatever the wrap, the last word must not become a part header
        doc["modules"][0]["spoken"] = ("word " * width).strip() + " the plan is as follows:"
        out = tmp_path / "module-intros.md"
        intros_file.write(out, doc)
        assert intros_file.read(out)["modules"][0]["spoken"] == doc["modules"][0]["spoken"]
        assert intros.load(out)[1]["spoken"] == doc["modules"][0]["spoken"]
