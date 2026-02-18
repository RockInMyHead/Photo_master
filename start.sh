#!/bin/bash
# Photo Master — запуск backend и frontend
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Запуск backend на http://localhost:8001 ..."
(cd "$ROOT/backend" && ./venv/bin/python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001) &
BACKEND_PID=$!

sleep 6
echo "🚀 Запуск frontend на http://localhost:5173 ..."
cd "$ROOT/frontend" && npm run dev
