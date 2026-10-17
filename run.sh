#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/python scripts/init_demo.py
echo 'Read runtime/bootstrap-credentials.txt for your local demo accounts.'
echo 'Open http://127.0.0.1:8000 after the server starts.'
.venv/bin/python -m agent.daemon &
agent_pid=$!
trap 'kill "$agent_pid" 2>/dev/null || true; wait "$agent_pid" 2>/dev/null || true' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
AEGIS_EMBEDDED_AGENT=false .venv/bin/python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
