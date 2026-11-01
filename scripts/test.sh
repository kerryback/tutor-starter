#!/usr/bin/env bash
# Run the tests: the engine's and each tutor's own, for one tutor or all of them.
#   scripts/test.sh            every tutor
#   scripts/test.sh binomial   one tutor
# The engine's tests use the binomial tutor as their example content, so they
# always run with it; each tutor's own tests run with that tutor.
set -uo pipefail
source "$(dirname "$0")/_common.sh"
cd "$ROOT"
tutors=("$@"); [ ${#tutors[@]} -eq 0 ] && tutors=($(all_tutors))
status=0
for t in "${tutors[@]}"; do need_tutor "$t"; done
echo "== the engine and binomial"
TUTOR_DIR="$ROOT/binomial" "$PY" -m pytest -q engine/tests binomial/tests || status=1
for t in "${tutors[@]}"; do
  [ "$t" = binomial ] || [ ! -d "$ROOT/$t/tests" ] && continue
  echo "== $t"
  TUTOR_DIR="$ROOT/$t" "$PY" -m pytest -q "$t/tests" || status=1
done
echo "== the home page (tutors.example.edu)"
"$PY" -m pytest -q home/tests || status=1
echo "== the review page"
"$PY" -m pytest -q review/tests || status=1
if command -v node >/dev/null; then
  echo "== the page (JavaScript)"
  node --test engine/tests/js/*.test.mjs review/tests/js/*.test.mjs 2>&1 | grep -E "^# (pass|fail)" || status=1
fi
exit $status
