"""Test setup for every tutor: the engine is importable, and TUTOR_DIR names
the tutor under test (binomial unless set, e.g. TUTOR_DIR=<tutor>)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
os.environ.setdefault("TUTOR_DIR", str(ROOT / "binomial"))
sys.path.insert(0, str(ROOT / "engine"))
