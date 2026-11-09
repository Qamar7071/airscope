#!/usr/bin/env bash
# AirScope one-command launcher.
#
#   scripts/start.sh          # install if needed, build the UI, serve everything on http://127.0.0.1:8000
#   scripts/start.sh dev      # backend on :8000 + Vite dev server with hot reload on http://127.0.0.1:5173
#
# Works fully offline after dependencies are installed (map tiles need internet; data does not).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-prod}"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"

say() { printf '\033[1;36m[airscope]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[airscope]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- python
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || die "Python 3.11+ is required (set PYTHON=/path/to/python3.11)."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || die "Python 3.11+ is required, found $("$PY" --version 2>&1)."

if [ ! -x "$VENV/bin/python" ]; then
  say "Creating Python virtual environment in backend/.venv"
  "$PY" -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c "import flask, sklearn, pandas" >/dev/null 2>&1; then
  say "Installing backend dependencies"
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV/bin/python" -m pip install -r "$BACKEND/requirements.txt"
  "$VENV/bin/python" -m pip install -r "$BACKEND/requirements-optional.txt" || say "Optional XGBoost not installed - the ensemble will use two models."
fi

# ---------------------------------------------------------------- node
command -v npm >/dev/null 2>&1 || die "Node.js 18+ with npm is required for the web interface."
if [ ! -d "$FRONTEND/node_modules" ]; then
  say "Installing frontend dependencies"
  (cd "$FRONTEND" && npm install --no-audit --no-fund)
fi

if [ "$MODE" = "dev" ]; then
  say "Starting backend on http://${AIRSCOPE_HOST:-127.0.0.1}:${AIRSCOPE_PORT:-8000} (models train in the background on first run)"
  (cd "$BACKEND" && exec "$VENV/bin/python" app.py) &
  BACK_PID=$!
  trap 'kill "$BACK_PID" 2>/dev/null || true' EXIT INT TERM
  say "Starting the Vite dev server on http://127.0.0.1:5173"
  cd "$FRONTEND" && npm run dev
else
  if [ ! -f "$FRONTEND/dist/index.html" ] || [ -n "$(find "$FRONTEND/src" -newer "$FRONTEND/dist/index.html" -print -quit 2>/dev/null)" ]; then
    say "Building the web interface"
    (cd "$FRONTEND" && npm run build)
  fi
  say "AirScope is starting on http://${AIRSCOPE_HOST:-127.0.0.1}:${AIRSCOPE_PORT:-8000}"
  say "First run trains one model per city (about a minute each; progress is shown in the UI)."
  cd "$BACKEND" && exec "$VENV/bin/python" app.py
fi
