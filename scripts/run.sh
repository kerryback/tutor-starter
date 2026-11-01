#!/usr/bin/env bash
# Run a tutor on this computer, with voice, and open it in the browser.
#   scripts/run.sh binomial [port]
# You are signed in as a local test student.  With TUTORS_DEV=1, sign-in goes
# through the home app instead: run scripts/run-home.sh first.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_tutor "${1:-}"
PORT="${2:-8010}"
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "Set ANTHROPIC_API_KEY (or ANTHROPIC_KEY) first."; exit 1; }
SIGNIN=()
if [ "${TUTORS_DEV:-}" = 1 ]; then
  SIGNIN=(TUTORS_DEV=1 "TUTORS_SECRET=${TUTORS_SECRET:-dev}" "TUTORS_HOME=${TUTORS_HOME:-http://localhost:8060}")
else
  unset TUTORS_SECRET
  SIGNIN=(TUTORS_LOCAL=1)
fi
echo "Starting the $1 tutor at http://localhost:$PORT  (Ctrl-C stops it)"
( sleep 4; [ -n "${NO_OPEN:-}" ] || open "http://localhost:$PORT" 2>/dev/null || true ) &
cd "$ROOT/engine"
exec env TUTOR_DIR="$ROOT/$1" VOICE_ENABLED=1 ${SIGNIN[@]+"${SIGNIN[@]}"} \
  "$ROOT/.venv/bin/uvicorn" app:app --host 127.0.0.1 --port "$PORT"
