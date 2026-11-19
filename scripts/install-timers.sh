#!/usr/bin/env bash
# Copyright (c) 2026 Stefan Koelle (https://stefankoelle.de)
# Licensed under the MIT License. See LICENSE file in project root for details.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
TRIGGER="$REPO_DIR/scripts/trigger-deploy.sh"

command -v systemctl >/dev/null || { echo "systemctl nicht gefunden"; exit 1; }
[ -x "$TRIGGER" ] || { echo "Nicht ausführbar: $TRIGGER"; exit 1; }

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/darts-dispatch.service" <<EOF
[Unit]
Description=Trigger daily darts calendar deploy

[Service]
Type=oneshot
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=$TRIGGER
EOF

cat > "$UNIT_DIR/darts-dispatch.timer" <<'EOF'
[Unit]
Description=Daily trigger for darts calendar deploy

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now darts-dispatch.timer
systemctl --user list-timers darts-dispatch.timer
