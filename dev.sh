#!/usr/bin/env bash
# Dev: FastAPI with --reload (serves the UI from backend/web + the API).
set -euo pipefail
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] && { set -a; . ./.env; set +a; }
exec uvicorn main:app --reload --host 127.0.0.1 --port "${PORT:-8000}"
