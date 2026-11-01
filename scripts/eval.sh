#!/usr/bin/env bash
# Run a tutor's evals against the real model (this costs money: about $0.50 a run).
#   scripts/eval.sh binomial              every scenario
#   scripts/eval.sh binomial calibration  one scenario
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_tutor "${1:-}"
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "Set ANTHROPIC_API_KEY (or ANTHROPIC_KEY) first."; exit 1; }
t="$1"; shift
TUTOR_DIR="$ROOT/$t" "$PY" "$ROOT/evals/run_evals.py" "$@"
