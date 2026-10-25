#!/usr/bin/env bash
# Headless extraction wrapper: ./extract.sh <youtube-url> [--lang Romanian] [--open]
# Prints the path to the generated summary.html on stdout.
set -euo pipefail
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] && set -a && . ./.env && set +a || true
exec python -m extractor.cli "$@"
