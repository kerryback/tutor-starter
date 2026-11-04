# Shared by the scripts: the repo root, the Python in .venv, and the tutor folders.
# Runs in bash on macOS and Linux, and in Git Bash on Windows (the shell Claude Code uses there).
# On Windows, pwd -W gives C:/... paths, which both bash and Python understand.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/.venv/Scripts/python.exe"   # Windows
else
  PY="$ROOT/.venv/bin/python"           # macOS and Linux
fi
[ -x "$PY" ] || { echo "No .venv yet. Run scripts/setup.sh first."; exit 1; }
export PYTHONUTF8=1   # read and write files as UTF-8 on Windows too

# Open a page in the default browser, on any system.  NO_OPEN=1 skips it.
open_url() {
  [ -n "${NO_OPEN:-}" ] || "$PY" -m webbrowser "$1" >/dev/null 2>&1 || true
}

# The settings in site.toml, as shell variables.  Deploying needs a real domain
# (read_site any: a trial deploy, which needs none).
read_site() {
  eval "$("$PY" - "$ROOT/site.toml" <<'PYEOF'
import shlex, sys, tomllib
s = tomllib.load(open(sys.argv[1], "rb"))["site"]
for k, v in s.items():
    if isinstance(v, bool):
        v = "1" if v else ""
    print(f"SITE_{k.upper()}={shlex.quote(str(v))}")
PYEOF
)"
  if [ "$SITE_DOMAIN" = tutors.example.edu ] && [ "${1:-}" != any ]; then
    echo "Set your own domain in site.toml first."; exit 1
  fi
}

# Every folder with a tutor.toml is a tutor.
all_tutors() { for f in "$ROOT"/*/tutor.toml; do basename "$(dirname "$f")"; done; }

need_tutor() {
  [ -n "$1" ] && [ -f "$ROOT/$1/tutor.toml" ] && return
  echo "Name a tutor. Tutors: $(all_tutors | tr '\n' ' ')"; exit 1
}

# The local key: ANTHROPIC_API_KEY, or ANTHROPIC_KEY if that is what the shell has.
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -n "${ANTHROPIC_KEY:-}" ]; then export ANTHROPIC_API_KEY="$ANTHROPIC_KEY"; fi

# ---- Railway: used by scripts/deploy.sh and scripts/deploy-home.sh ----
# Railway's region IDs.  EU West (Amsterdam) is europe-west4-drams3a.
RAILWAY_REGIONS="us-west2 us-east4-eqdc4a europe-west4-drams3a asia-southeast1-eqsg3a"

# The Railway CLI (version 5 or later), signed in.  The secrets the deploys
# send come from deploy.env (Git ignores it) or the shell.
need_railway() {
  command -v railway >/dev/null 2>&1 || { echo "Install the Railway CLI first (see Deploying in README.md)."; exit 1; }
  local v; v=$(railway --version 2>/dev/null | awk '{print $2}')
  [ "${v%%.*}" -ge 5 ] 2>/dev/null || { echo "Railway CLI $v is too old. Update it to version 5 or later (brew upgrade railway, or npm i -g @railway/cli)."; exit 1; }
  railway whoami >/dev/null 2>&1 || { echo "Sign in to Railway first: railway login"; exit 1; }
  if [ -f "$ROOT/deploy.env" ]; then set -a; . "$ROOT/deploy.env"; set +a; fi
}

# Link the current folder to Railway project $1 and its service "web".  The
# first time, create them: one instance in region $2, and a volume at /data.
railway_setup() {
  local project="$1" region="$2" r zeros=()
  if ! railway link --project "$project" --environment production >/dev/null 2>&1; then
    echo "Creating the Railway project $project"
    railway init --name "$project" ${SITE_RAILWAY_WORKSPACE:+--workspace "$SITE_RAILWAY_WORKSPACE"} >/dev/null
  fi
  if ! railway service link web >/dev/null 2>&1; then
    railway add --service web >/dev/null   # creates the service and links it
    # One instance in the region.  REGION=0 removes a region, such as the
    # account's default one.  The region is set before the volume exists,
    # because a volume follows its service's region.
    for r in $RAILWAY_REGIONS; do [ "$r" = "$region" ] || zeros+=("$r=0"); done
    railway scale --service web "$region=1" "${zeros[@]}" >/dev/null \
      || railway scale --service web "$region=1" >/dev/null
    echo "The service runs in $region"
  fi
  if ! railway volume list --json 2>/dev/null | "$PY" -c '
import json, sys
sys.exit(not any(v.get("mountPath") == "/data" for v in json.load(sys.stdin).get("volumes", [])))'; then
    echo "Adding the volume at /data (the plan's size: 5 GB on Hobby)"
    railway volume add --mount-path /data >/dev/null
  fi
}

# Set plain variables (KEY=VALUE ...) on the linked service, without a deploy.
railway_vars() { railway variable set "$@" --skip-deploys >/dev/null; }

# Secrets (by name): each one the service lacks is set from this computer.
# One it has already is left alone; change it with railway variable set.
railway_secrets() {
  local have k
  have=" $(railway variable list --json | "$PY" -c 'import json, sys; print(" ".join(json.load(sys.stdin)))') "
  for k in "$@"; do
    case "$have" in *" $k "*) continue ;; esac
    [ -n "${!k:-}" ] || { echo "$k is not set on Railway or here. Put it in deploy.env (see README.md)."; exit 1; }
    printf '%s' "${!k}" | railway variable set "$k" --stdin --skip-deploys >/dev/null
    echo "Set the secret $k"
  done
}

# The address $1 on the linked service, on port 8000.  The first time, Railway
# prints the DNS records (a CNAME and a TXT) to add at the DNS provider.
railway_domain() {
  if railway domain status "$1" --service web >/dev/null 2>&1; then
    echo "The domain $1 is already on the service. Its DNS status: railway domain status $1"
  else
    railway domain "$1" --port 8000 --service web
    echo "Add the records above at your DNS provider. Check them with: railway domain status $1"
  fi
}

# Upload the current folder and build it with its Dockerfile.  Waits until the
# deploy succeeds or fails, and exits non-zero if it fails.
railway_up() { railway up --ci --service web --message "$1"; }
