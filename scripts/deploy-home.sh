#!/usr/bin/env bash
# Deploy the home app in home/ to Railway, at the domain in site.toml.
#   scripts/deploy-home.sh               deploy
#   scripts/deploy-home.sh --build-only  build the image here with Docker, to check it
# The home app is its own Railway project, tutors-home, with one service, "web",
# in EU West (Amsterdam), with a volume at /data for the accounts.  The secrets
# TUTORS_SECRET (shared with every tutor), TUTORS_PEPPER and SMTP_PASSWORD come
# from deploy.env or the shell the first time.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
PROJECT=tutors-home REGION=europe-west4-drams3a

BUILD=$(mktemp -d)
# On exit, forget the folder's Railway link, then remove the folder.
trap '(cd "$BUILD" && railway unlink --yes >/dev/null 2>&1); rm -rf "$BUILD"' EXIT
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
need_railway
cd "$BUILD"
railway_setup "$PROJECT" "$REGION"
railway_vars PORT=8000 HOME_DATA_DIR=/data \
  "TUTORS_HOME=https://$SITE_DOMAIN" "TUTORS_COOKIE_DOMAIN=$SITE_DOMAIN" \
  "TUTORS_EMAIL_DOMAIN=$SITE_EMAIL_DOMAIN" \
  "SMTP_HOST=$SITE_SMTP_HOST" "SMTP_PORT=$SITE_SMTP_PORT" "SMTP_USER=$SITE_SMTP_USER" \
  "MAIL_FROM=$SITE_MAIL_FROM"
railway_secrets TUTORS_SECRET TUTORS_PEPPER SMTP_PASSWORD

echo "Deploying the home app to the Railway project $PROJECT"
railway_up home
railway_domain "$SITE_DOMAIN"
echo "Live at https://$SITE_DOMAIN once its DNS records are in place."
