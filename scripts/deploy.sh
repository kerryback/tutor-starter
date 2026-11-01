#!/usr/bin/env bash
# Deploy one tutor to Koyeb, using the [deploy] settings in its tutor.toml.
#   scripts/deploy.sh binomial
# Builds a folder with engine/, instructions/ and the tutor (as tutor/), and
# deploys it with Koyeb's Docker builder.  site.toml holds the domain and model.
# Every tutor uses the same Koyeb secrets: tutors-anthropic-key for the model and
# tutors-session-secret, which checks the sign-in cookie from the home app (see
# engine/auth.py).
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_tutor "${1:-}"
t="$1"
read_site
read -r APP SERVICE VOLUME INSTANCE REGION TITLE < <("$PY" - "$ROOT/$t/tutor.toml" <<'PYEOF'
import sys, tomllib
c = tomllib.load(open(sys.argv[1], "rb")); d = c["deploy"]
print(d["app"], d.get("service", "web"), d["volume"], d.get("instance", "medium"),
      d.get("region", "fra"), c["title"])
PYEOF
)
DOMAIN="$t.$SITE_DOMAIN"

VOLUMES=$(koyeb volumes list 2>/dev/null || true)
if ! grep -qw "$VOLUME" <<<"$VOLUMES"; then
  echo "Creating the 5 GB volume $VOLUME (student records and the speech models)"
  koyeb volumes create "$VOLUME" --region "$REGION" --size 5
fi

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
cp -R "$ROOT/engine" "$ROOT/instructions" "$BUILD/"
cp -R "$ROOT/$t" "$BUILD/tutor"
cp "$ROOT/Dockerfile" "$ROOT/requirements.txt" "$ROOT/.dockerignore" "$BUILD/"
rm -rf "$BUILD/engine/tests" "$BUILD/engine/data" "$BUILD/tutor/data"
find "$BUILD" -name __pycache__ -prune -exec rm -rf {} +

echo "Deploying $t to Koyeb app $APP ($DOMAIN)"
EXTRA=()
[ -n "${SITE_ELEVENLABS:-}" ] && EXTRA+=(--env 'ELEVENLABS_API_KEY={{secret.elevenlabs-api-key}}')
[ -n "${SITE_ANTHROPIC_BASE_URL:-}" ] && EXTRA+=(--env "ANTHROPIC_BASE_URL=$SITE_ANTHROPIC_BASE_URL")
koyeb deploy "$BUILD" "$APP/$SERVICE" --archive-builder docker \
  --instance-type "$INSTANCE" --regions "$REGION" --ports 8000:http --routes /:8000 \
  --min-scale 1 --max-scale 1 --volumes "$VOLUME:/data" --env VOICE_ENABLED=1 \
  --env 'ANTHROPIC_API_KEY={{secret.tutors-anthropic-key}}' \
  --env 'TUTORS_SECRET={{secret.tutors-session-secret}}' \
  --env "TUTORS_HOME=https://$SITE_DOMAIN" --env "TUTORS_COOKIE_DOMAIN=$SITE_DOMAIN" \
  --env "TUTOR_MODEL=$SITE_MODEL" --env "TUTOR_EFFORT=$SITE_EFFORT" --env DATA_DIR=/data \
  ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 | grep -v -E "new version|update instructions"
echo "Koyeb is building it. It is live in a few minutes at https://$DOMAIN"
