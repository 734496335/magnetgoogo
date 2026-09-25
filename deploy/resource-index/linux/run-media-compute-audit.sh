#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=${APP_ROOT:-/opt/magnet-media-finalizer/app}
export MAGNET_MEDIA_FINALIZER_MODE=candidate
export MAGNET_MEDIA_FINALIZER_STATUS_FILE=${MAGNET_MEDIA_FINALIZER_STATUS_FILE:-/var/lib/magnet-media/status/latest-compute-audit.json}

exec /usr/bin/bash "$APP_ROOT/deploy/resource-index/linux/run-media-compute-finalizer.sh"
