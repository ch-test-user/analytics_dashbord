#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

PORT="${PORT:-8501}"
PYTHON_BIN="${PYTHON_BIN:-}"

find_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    command -v "$PYTHON_BIN"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi

  echo "Python was not found. Install Python 3.10+ and rerun this script." >&2
  exit 1
}

PYTHON="$(find_python)"

echo "Using Python: $PYTHON"
"$PYTHON" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required.")
print(f"Python version: {sys.version.split()[0]}")
PY

if [[ ! -d ".venv" ]]; then
  echo "Creating virtual environment..."
  "$PYTHON" -m venv .venv
fi

VENV_PYTHON=".venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Virtual environment python not found at $VENV_PYTHON" >&2
  exit 1
fi

echo "Installing dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install --upgrade --force-reinstall -r requirements.txt

echo "Verifying Streamlit installation..."
"$VENV_PYTHON" - <<'PY'
from pathlib import Path
import streamlit

index = Path(streamlit.__file__).resolve().parent / "static" / "index.html"
if not index.exists():
    raise SystemExit(f"Streamlit static asset missing: {index}")
print(f"Streamlit version: {streamlit.__version__}")
PY

echo "Starting dashboard on http://localhost:${PORT}"
exec "$VENV_PYTHON" -m streamlit run streamlit_app.py \
  --server.headless true \
  --server.port "$PORT"
