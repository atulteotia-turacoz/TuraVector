#!/usr/bin/env bash
# Start the TuraDome API on http://localhost:8001
cd "$(dirname "$0")"
[ -d venv ] || { python3 -m venv venv && ./venv/bin/pip install -r requirements.txt; }
exec ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
