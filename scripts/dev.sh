#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Python env missing. Run: make setup" >&2
  exit 1
fi
if [[ ! -d banks-ui/node_modules ]]; then
  echo "UI dependencies missing. Run: make setup" >&2
  exit 1
fi

export IAI_BANK_UI_BASE_URL="${IAI_BANK_UI_BASE_URL:-http://127.0.0.1:5173}"

cleanup() {
  trap - INT TERM EXIT
  kill 0 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "API  http://127.0.0.1:8000/docs"
echo "UI   http://127.0.0.1:5173"
echo ""

.venv/bin/uvicorn interfaces_ai.api.app:app --reload --host 127.0.0.1 --port 8000 &
(cd banks-ui && npm run dev) &
wait
