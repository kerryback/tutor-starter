#!/usr/bin/env bash
# Deploy the home app in home/ to Koyeb, at the domain in site.toml.
#   scripts/deploy-home.sh               deploy
#   scripts/deploy-home.sh --build-only  build the image here with Docker, to check it
# The Koyeb secrets tutors-session-secret (shared with every tutor),
# tutors-pepper and tutors-smtp-password must exist.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
APP=tutors-home SERVICE=web VOLUME=tutors-home-data INSTANCE=micro REGION=fra

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
cp -R "$ROOT/home/." "$BUILD/"
cp "$ROOT/engine/session_cookie.py" "$BUILD/"
rm -rf "$BUILD/tests" "$BUILD/data" "$BUILD/__init__.py"
find "$BUILD" -name __pycache__ -prune -exec rm -rf {} +

if [ "${1:-}" = --build-only ]; then
  docker build -t tutors-home "$BUILD"
  docker run --rm -e TUTORS_DEV=1 tutors-home python -c "import app; print('image ok')"
  exit
fi

read_site
VOLUMES=$(koyeb volumes list 2>/dev/null || true)
if ! grep -qw "$VOLUME" <<<"$VOLUMES"; then
  echo "Creating the 1 GB volume $VOLUME (the accounts)"
  koyeb volumes create "$VOLUME" --region "$REGION" --size 1
fi

echo "Deploying the home app to Koyeb app $APP ($SITE_DOMAIN)"
koyeb deploy "$BUILD" "$APP/$SERVICE" --archive-builder docker \
  --instance-type "$INSTANCE" --regions "$REGION" --ports 8000:http --routes /:8000 \
  --min-scale 1 --max-scale 1 --volumes "$VOLUME:/data" \
  --env 'TUTORS_SECRET={{secret.tutors-session-secret}}' \
  --env 'TUTORS_PEPPER={{secret.tutors-pepper}}' \
  --env "TUTORS_HOME=https://$SITE_DOMAIN" --env "TUTORS_COOKIE_DOMAIN=$SITE_DOMAIN" \
  --env "TUTORS_EMAIL_DOMAIN=$SITE_EMAIL_DOMAIN" \
  --env "SMTP_HOST=$SITE_SMTP_HOST" --env "SMTP_PORT=$SITE_SMTP_PORT" --env "SMTP_USER=$SITE_SMTP_USER" \
  --env 'SMTP_PASSWORD={{secret.tutors-smtp-password}}' \
  --env "MAIL_FROM=$SITE_MAIL_FROM" --env HOME_DATA_DIR=/data \
  2>&1 | grep -v -E "new version|update instructions"
echo "Koyeb is building it. It is live in a few minutes at https://$SITE_DOMAIN"
