#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -d -m 0755 /opt/magnet-source-sync
install -d -m 0700 /etc/magnet-source-sync
if [[ ! -f /etc/magnet-source-sync/source-sync.env ]]; then
  echo "missing /etc/magnet-source-sync/source-sync.env with SOURCE_ENCRYPTION_KEY_HEX" >&2
  exit 1
fi
chmod 0600 /etc/magnet-source-sync/source-sync.env
install -m 0755 "$SOURCE_DIR/sync-source-packs.sh" /opt/magnet-source-sync/sync-source-packs.sh
install -m 0755 "$SOURCE_DIR/verify-source-packs.py" /opt/magnet-source-sync/verify-source-packs.py
install -m 0644 "$SOURCE_DIR/magnet-source-sync.service" /etc/systemd/system/magnet-source-sync.service
install -m 0644 "$SOURCE_DIR/magnet-source-sync.timer" /etc/systemd/system/magnet-source-sync.timer
systemctl daemon-reload
systemctl enable --now magnet-source-sync.timer
systemctl reset-failed magnet-source-sync.service 2>/dev/null || true
systemctl start magnet-source-sync.service
