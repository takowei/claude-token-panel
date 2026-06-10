#!/usr/bin/env bash
set -e

PYLIB="${TMPDIR:-/tmp}/pylib-token-panel"

if [ ! -d "$PYLIB" ]; then
  echo "Installing fastapi + uvicorn to $PYLIB ..."
  python3 /usr/share/python-wheels/pip-22.0.2-py3-none-any.whl/pip \
    install fastapi uvicorn --target "$PYLIB" -q
fi

echo "Starting Claude Token Panel on http://0.0.0.0:8765 ..."
PYTHONPATH="$PYLIB" exec python3 "$(dirname "$0")/main.py"
