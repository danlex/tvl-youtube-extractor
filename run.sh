#!/usr/bin/env bash
# One-command local app: builds the UI, sets up the backend, serves both at :8000.
set -euo pipefail
cd "$(dirname "$0")"

# 0. Preflight: the pipeline shells out to these.
missing=""
for bin in yt-dlp ffmpeg ffprobe whisper-cli; do
  command -v "$bin" >/dev/null 2>&1 || missing="$missing $bin"
done
[ -n "$missing" ] && echo "[warn] missing on PATH:$missing (install before extracting)"

# 1. Build the Next.js static export (once; delete frontend/out to rebuild).
if command -v npm >/dev/null 2>&1; then
  if [ ! -d frontend/out ]; then
    echo "[web] building frontend…"
    ( cd frontend && npm install && npm run build )
  fi
else
  echo "[web] npm not found — UI won't be served. Install Node 18+ and rerun."
fi

# 2. Backend venv + deps.
cd backend
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 3. Serve API + built UI.
envflag=""
[ -f .env ] && envflag="--env-file .env"
echo "[app] open http://localhost:8000"
exec uvicorn main:app --host 127.0.0.1 --port 8000 $envflag
