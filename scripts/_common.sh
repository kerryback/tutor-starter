# Shared by the scripts: the repo root, the Python in .venv, and the tutor folders.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "No .venv yet. Run scripts/setup.sh first."; exit 1; }

# The settings in site.toml, as shell variables.  Deploying needs a real domain.
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
  if [ "$SITE_DOMAIN" = tutors.example.edu ]; then
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
