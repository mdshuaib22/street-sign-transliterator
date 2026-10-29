#!/bin/bash
echo "=========================================="
echo "  SignLens - Installing & Starting"
echo "=========================================="
echo ""
echo "Step 1: Installing Python packages..."
cd "$(dirname "$0")"

# Use the project venv if present (created via `uv venv` / `python -m venv .venv`),
# otherwise fall back to the system interpreter.
if [ -f ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
else
  PY="python"
fi

"$PY" -m pip install -r requirements.txt
echo ""
echo "Step 2: Starting server..."
echo ""
echo "  Open your browser at: http://localhost:8000"
echo "  Press Ctrl+C to stop"
echo ""
"$PY" -m uvicorn main:app --reload --port 8000
