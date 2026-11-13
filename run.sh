#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=python3
if [ -x .venv/bin/python3 ]; then
    PYTHON=.venv/bin/python3
fi

OUT_DIR="dist"

"$PYTHON" fetch_termine.py --out-dir "$OUT_DIR" --html-out "$OUT_DIR/index.html"
