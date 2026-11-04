#!/usr/bin/env bash
# Run tutors.example.edu (the home app in home/) on this computer.
#   scripts/run-home.sh [port]
# The accounts go in home/data/, and the emailed links are printed here
# instead of sent.  To try the round trip with a tutor, run that tutor with
#   TUTORS_DEV=1 scripts/run.sh binomial
set -euo pipefail
source "$(dirname "$0")/_common.sh"
PORT="${1:-8060}"
echo "Starting the home page at http://localhost:$PORT  (Ctrl-C stops it)"
( sleep 2; open_url "http://localhost:$PORT" ) &
cd "$ROOT/home"
TUTORS_DEV=1 TUTORS_SECRET="${TUTORS_SECRET:-dev}" TUTORS_PEPPER="${TUTORS_PEPPER:-dev}" \
  TUTORS_HOME="http://localhost:$PORT" HOME_DATA_DIR="$ROOT/home/data" \
  exec "$PY" -m uvicorn app:app --host 127.0.0.1 --port "$PORT"
