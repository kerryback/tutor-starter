#!/usr/bin/env bash
# After a change to engine/ or instructions/: test every tutor, then redeploy
# every tutor.  Stops before deploying anything if a test fails.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
"$ROOT/scripts/test.sh"
for t in $(all_tutors); do
  "$ROOT/scripts/deploy.sh" "$t"
done
