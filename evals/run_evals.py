"""Behavior evals for a tutor.  These call the Claude API and cost money
(roughly $0.50 per full run).

    scripts/eval.sh binomial              # every scenario for the binomial tutor
    scripts/eval.sh binomial diagnose     # one scenario

Each scenario plays a scripted student against the real agent, in voice mode,
and applies deterministic checks to what the student would see and hear.  The
general scenarios are in harness.py; the tutor's own are in <tutor>/evals.py.
Results are written to evals/results/.
"""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "evals"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import harness  # noqa: E402
import tutor_config as cfg  # noqa: E402
from tutor import Store, Tutor  # noqa: E402

own = cfg.DIR / "evals.py"
if own.exists():
    spec = importlib.util.spec_from_file_location("tutor_evals", own)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


async def main(names):
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    results, failed = {}, 0
    with tempfile.TemporaryDirectory() as tmp:
        tutor = Tutor(Store(tmp), voice=True)
        for name in names:
            student = tutor.store.load(f"eval {name}")
            turns, checks = await harness.SCENARIOS[name](tutor, student)
            checks = {"no service errors": not any(t["errors"] for t in turns), **checks}
            checks["no symbols in any spoken sentence"] = harness.speech_is_clean(turns)
            checks["every spoken number is on the board"] = harness.numbers_on_board(turns)
            checks["every board formula is also said in words"] = harness.formulas_are_read_aloud(turns)
            results[name] = {"checks": checks, "turns": turns, "tool_calls": harness.tool_calls(student)}
            print(f"\n== {name}")
            for k, ok in checks.items():
                print(f"  {'PASS' if ok else 'FAIL'}  {k}")
                failed += not ok
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}-{cfg.NAME}.json"
    path.write_text(json.dumps(results, indent=1, default=str))
    print(f"\n{failed} failed check(s). Transcripts: {path}")
    return failed


if __name__ == "__main__":
    names = sys.argv[1:] or list(harness.SCENARIOS)
    unknown = [n for n in names if n not in harness.SCENARIOS]
    if unknown:
        sys.exit(f"No scenario {', '.join(unknown)}. Scenarios: {', '.join(harness.SCENARIOS)}")
    sys.exit(1 if asyncio.run(main(names)) else 0)
