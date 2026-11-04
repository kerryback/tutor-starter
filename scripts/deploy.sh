#!/usr/bin/env bash
# Deploy one tutor to Railway, using the [deploy] settings in its tutor.toml.
#   scripts/deploy.sh binomial           deploy at binomial.<domain in site.toml>
#   scripts/deploy.sh binomial --trial [name]
#       deploy to a separate project (<project>-trial, or the name given) at a
#       Railway address, with no DNS.  Signing in does not work there, but
#       /api/config shows whether the tutor and its voice are up.
# Builds a folder with engine/, instructions/ and the tutor (as tutor/), and
# uploads it to Railway, which builds it with the Dockerfile.  Each tutor is its
# own Railway project with one service, "web": one instance, in the region in
# tutor.toml, with a volume at /data for the student records and the speech
# models.  site.toml holds the domain and model.  The secrets ANTHROPIC_API_KEY
# and TUTORS_SECRET (shared with the home app; it checks the sign-in cookie, see
# engine/auth.py) come from deploy.env or the shell the first time.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_tutor "${1:-}"
t="$1"
TRIAL=""; [ "${2:-}" = --trial ] && TRIAL=1
if [ -n "$TRIAL" ]; then read_site any; else read_site; fi
need_railway
read -r PROJECT REGION < <("$PY" - "$ROOT/$t/tutor.toml" <<'PYEOF'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], "rb"))["deploy"]
print(d["project"], d.get("region", "europe-west4-drams3a"))
PYEOF
)
[ -n "$TRIAL" ] && PROJECT="${3:-$PROJECT-trial}"
DOMAIN="$t.$SITE_DOMAIN"

BUILD=$(mktemp -d)
# On exit, forget the folder's Railway link, then remove the folder.
trap '(cd "$BUILD" && railway unlink --yes >/dev/null 2>&1); rm -rf "$BUILD"' EXIT
cp -R "$ROOT/engine" "$ROOT/instructions" "$BUILD/"
cp -R "$ROOT/$t" "$BUILD/tutor"
cp "$ROOT/Dockerfile" "$ROOT/requirements.txt" "$ROOT/.dockerignore" "$BUILD/"
rm -rf "$BUILD/engine/tests" "$BUILD/engine/data" "$BUILD/tutor/data"
find "$BUILD" -name __pycache__ -prune -exec rm -rf {} +
cd "$BUILD"

railway_setup "$PROJECT" "$REGION"

VOICE="${SITE_VOICE:-}"; [ -z "$VOICE" ] && [ -n "${SITE_ELEVENLABS:-}" ] && VOICE=elevenlabs
VOICE="${VOICE:-kokoro}"
VARS=(PORT=8000 VOICE_ENABLED=1 DATA_DIR=/data "TUTOR_VOICE=$VOICE"
      "TUTORS_HOME=https://$SITE_DOMAIN" "TUTORS_COOKIE_DOMAIN=$SITE_DOMAIN"
      "TUTOR_MODEL=$SITE_MODEL" "TUTOR_EFFORT=$SITE_EFFORT")
[ -n "${SITE_ANTHROPIC_BASE_URL:-}" ] && VARS+=("ANTHROPIC_BASE_URL=$SITE_ANTHROPIC_BASE_URL")
railway_vars "${VARS[@]}"
SECRETS=(ANTHROPIC_API_KEY TUTORS_SECRET)
[ "$VOICE" = elevenlabs ] && SECRETS+=(ELEVENLABS_API_KEY)
railway_secrets "${SECRETS[@]}"

echo "Deploying $t to the Railway project $PROJECT"
railway_up "$t"
if [ -n "$TRIAL" ]; then
  railway domain --port 8000 --service web
  echo "Delete the trial with: railway delete --project $PROJECT --yes"
else
  railway_domain "$DOMAIN"
  echo "Live at https://$DOMAIN once its DNS records are in place."
fi
