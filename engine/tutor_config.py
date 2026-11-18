"""Which tutor this app serves.

TUTOR_DIR names the tutor's folder (for example ~/repos/tutors/binomial).  It
holds tutor.toml (names, reference files, deployment), content/ (topic.md,
module-intros.md and the teaching scripts) and topic.py (the tutor's own tools
and plots).  The shared instructions are in ../instructions, or INSTRUCTIONS_DIR.
"""

import os
import sys
import tomllib
from pathlib import Path

ENGINE = Path(__file__).parent
ROOT = ENGINE.parent

if not os.environ.get("TUTOR_DIR"):
    raise SystemExit("Set TUTOR_DIR to the tutor's folder, for example TUTOR_DIR=binomial.")
DIR = Path(os.environ["TUTOR_DIR"])
if not DIR.is_absolute():
    DIR = (Path.cwd() / DIR) if (Path.cwd() / DIR).exists() else ROOT / DIR
DIR = DIR.resolve()
CONTENT = DIR / "content"
INSTRUCTIONS = Path(os.environ.get("INSTRUCTIONS_DIR", ROOT / "instructions"))

CONFIG = tomllib.loads((DIR / "tutor.toml").read_text(encoding="utf-8"))
NAME = CONFIG["name"]
TITLE = CONFIG["title"]
SUBTITLE = CONFIG.get("subtitle", TITLE)
WHISPER_PROMPT = CONFIG.get("whisper_prompt", "")
SAY = CONFIG.get("say", {})   # how the voice says some words: {"CAPM": "cap-em"}
REFERENCES = CONFIG.get("references", [])

sys.path.insert(0, str(DIR))
import topic  # noqa: E402  the tutor's own tools: TOOLS, run, PLOTS, PLOT_PARAMS, make_plot
