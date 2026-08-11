#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -d -m 0755 /opt/magnet-source-sync
install -m 0755 "$SOURCE_DIR/sync-source-packs.sh" /opt/magnet-source-sync/sync-source-packs.sh
install -m 0644 "$SOURCE_DIR/magnet-source-sync.service" /etc/systemd/system/magnet-source-sync.service
install -m 0644 "$SOURCE_DIR/magnet-source-sync.timer" /etc/systemd/system/magnet-source-sync.timer
systemctl daemon-reload
systemctl enable --now magnet-source-sync.timer
systemctl reset-failed magnet-source-sync.service 2>/dev/null || true
systemctl start magnet-source-sync.service
