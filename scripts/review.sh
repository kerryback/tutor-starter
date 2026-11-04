#!/usr/bin/env bash
# Open the review page for one tutor: the intros, plots, examples, mistakes and explained code.
#   scripts/review.sh binomial [port]
# Edits on the page are saved to <tutor>/review.json and <tutor>/content/module-intros.md.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
T="${1:-}"
[ -n "$T" ] && [ -f "$ROOT/$T/review.json" ] || { echo "No ${T:-<tutor>}/review.json yet. The tutor skill writes it when it builds the tutor."; exit 1; }
PORT="${2:-8040}"
echo "Review page for $T at http://127.0.0.1:$PORT  (Ctrl-C stops it)"
( sleep 2; open_url "http://127.0.0.1:$PORT" ) &
cd "$ROOT"
exec "$PY" -m review.server "$ROOT/$T" --port "$PORT"
