#!/usr/bin/env bash
# Copyright (c) 2026 Stefan Koelle (https://stefankoelle.de)
# Licensed under the MIT License. See LICENSE file in project root for details.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=python3
if [ -x .venv/bin/python3 ]; then
    PYTHON=.venv/bin/python3
fi

OUT_DIR="dist"

"$PYTHON" fetch_termine.py --out-dir "$OUT_DIR" --html-out "$OUT_DIR/index.html"
