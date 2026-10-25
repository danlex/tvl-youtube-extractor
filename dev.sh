#!/usr/bin/env bash
# Dev mode: FastAPI with --reload on :8000, Next.js dev server on :3000.
# Open http://localhost:3000 (it talks to the backend via NEXT_PUBLIC_API_BASE).
set -euo pipefail
cd "$(dirname "$0")"

cd backend
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
envflag=""
[ -f .env ] && envflag="--env-file .env"
uvicorn main:app --reload --host 127.0.0.1 --port 8000 $envflag &
api=$!
trap 'kill $api 2>/dev/null || true' EXIT
cd ../frontend
[ -d node_modules ] || npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
