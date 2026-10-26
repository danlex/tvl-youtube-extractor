#!/usr/bin/env bash
# One command: set up the backend and serve the app (UI + API) at :8000.
set -euo pipefail
cd "$(dirname "$0")"

# Preflight — the pipeline shells out to these.
missing=""
for bin in yt-dlp ffmpeg ffprobe; do
  command -v "$bin" >/dev/null 2>&1 || missing="$missing $bin"
done
[ -n "$missing" ] && echo "[warn] missing on PATH:$missing  (brew install yt-dlp ffmpeg)"
if [ -z "${ANTHROPIC_API_KEY:-}" ] && ! command -v claude >/dev/null 2>&1; then
  echo "[warn] no ANTHROPIC_API_KEY and no 'claude' CLI — the agent step will fail."
fi

cd backend
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
[ -f .env ] && { set -a; . ./.env; set +a; }

echo "[app] open http://localhost:${PORT:-8000}"
exec uvicorn main:app --host 127.0.0.1 --port "${PORT:-8000}"
