#!/usr/bin/env bash
# The teacher's preview of a tutor (/tutor:edit): the tutor on this computer,
# with a Note button on the board.  Notes go to <tutor>/notes.jsonl, and the
# prompt is rebuilt at every turn, so an edit to the tutor's files applies at
# the tutor's next reply without a restart.
#   scripts/preview.sh capm [port]
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_tutor "${1:-}"
PORT="${2:-8010}"
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "Set ANTHROPIC_API_KEY (or ANTHROPIC_KEY) first."; exit 1; }
unset TUTORS_SECRET
echo "Previewing the $1 tutor at http://localhost:$PORT  (Ctrl-C stops it)"
( sleep 4; [ -n "${NO_OPEN:-}" ] || open "http://localhost:$PORT" 2>/dev/null || true ) &
cd "$ROOT/engine"
exec env TUTOR_DIR="$ROOT/$1" VOICE_ENABLED=1 TUTORS_LOCAL=1 TUTORS_TEACHER=1 \
  "$ROOT/.venv/bin/uvicorn" app:app --host 127.0.0.1 --port "$PORT"
