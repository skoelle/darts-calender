#!/usr/bin/env bash
# Copyright (c) 2026 Stefan Koelle (https://stefankoelle.de)
# Licensed under the MIT License. See LICENSE file in project root for details.
set -euo pipefail

REPO="skoelle/darts-calender"
echo "[$(date -Is)] dispatch deploy.yml on $REPO"
gh workflow run deploy.yml --repo "$REPO" --ref main
