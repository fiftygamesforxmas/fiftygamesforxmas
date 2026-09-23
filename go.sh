#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

pick_python() {
    if command -v python3 >/dev/null 2>&1; then
        echo python3
    elif command -v python >/dev/null 2>&1; then
        echo python
    else
        echo "Python 3 was not found. Install python3." >&2
        exit 1
    fi
}

PY="$(pick_python)"
echo "Using interpreter: $PY"

if [ ! -x "go_self_venv/bin/python" ] && [ ! -x "go_self_venv/bin/python3" ]; then
    echo "Creating virtual environment for go.py ..."
    "$PY" -m venv go_self_venv
fi

# shellcheck disable=SC1091
source "go_self_venv/bin/activate"

if command -v python3 >/dev/null 2>&1; then
    RUN_PY=python3
else
    RUN_PY=python
fi

"$RUN_PY" -m pip install --upgrade pip
"$RUN_PY" -m pip install pygame
exec "$RUN_PY" go.py "$@"