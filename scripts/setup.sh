#!/usr/bin/env bash
# First-time setup: the Python environment (.venv) and espeak-ng for the voice.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ ! -x .venv/bin/python ]; then
  PYTHON=$(command -v python3.13 || command -v python3.12 || command -v python3)
  echo "Creating .venv with $PYTHON"
  "$PYTHON" -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
for req in "$ROOT"/*/requirements.txt; do
  [ -f "$req" ] || continue
  echo "Installing $(basename "$(dirname "$req")")'s packages"
  .venv/bin/pip install -q -r "$req"
done
if ! command -v espeak-ng >/dev/null; then
  echo "The voice needs espeak-ng. Install it with: brew install espeak-ng"
fi
command -v node >/dev/null || echo "The page's tests need Node. Install it with: brew install node"
echo "Setup done."
