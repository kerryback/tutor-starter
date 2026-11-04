#!/usr/bin/env bash
# After a change to engine/ or instructions/: test every tutor, then redeploy
# every tutor to Railway.  Stops before deploying anything if a test fails.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
read_site
need_railway   # check the CLI and the sign-in before the tests, not after
"$ROOT/scripts/test.sh"
for t in $(all_tutors); do
  "$ROOT/scripts/deploy.sh" "$t"
done
