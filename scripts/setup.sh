#!/usr/bin/env bash
# First-time setup: the Python environment (.venv) and every tutor's packages.
# Works on macOS, Linux, and Windows (in Git Bash, the shell Claude Code uses there).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  # The first Python that is 3.11 or later (tomllib).  "py -3" is the Windows launcher.
  PYTHON=""
  for c in python3.13 python3.12 python3.11 python3 python "py -3"; do
    if $c -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
      PYTHON="$c"; break
    fi
  done
  if [ -z "$PYTHON" ]; then
    echo "The tutors need Python 3.11 or later. Install it from python.org."
    echo "On Windows, tick \"Add python.exe to PATH\" in the installer, then open a new terminal."
    exit 1
  fi
  echo "Creating .venv with $PYTHON"
  $PYTHON -m venv .venv
fi
source scripts/_common.sh
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt
for req in "$ROOT"/*/requirements.txt; do
  [ -f "$req" ] || continue
  echo "Installing $(basename "$(dirname "$req")")'s packages"
  "$PY" -m pip install -q -r "$req"
done
# The voice uses the espeak-ng that comes with the kokoro-onnx package, so no
# separate install is needed.  A system espeak-ng, if there is one, is used first.
command -v node >/dev/null || echo "The page's tests need Node. Install it from nodejs.org or with your package manager."
echo "Setup done."
