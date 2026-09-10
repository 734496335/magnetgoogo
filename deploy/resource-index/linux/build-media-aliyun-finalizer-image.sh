#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_RELEASE=${APP_RELEASE:-$(cd -- "$SCRIPT_DIR/../../.." && pwd)}
release_name=$(basename "$APP_RELEASE")
IMAGE=${MAGNET_MEDIA_FINALIZER_IMAGE:-magnet-media-finalizer:$release_name}

[[ -d "$APP_RELEASE" && "$release_name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid APP_RELEASE" >&2; exit 2; }
[[ "$(uname -m)" == "x86_64" ]] || { echo "Aliyun finalizer image must be built natively on x86_64" >&2; exit 2; }
[[ -f "$APP_RELEASE/deploy/resource-index/linux/Dockerfile" ]] || { echo "media Dockerfile is missing" >&2; exit 2; }

/usr/bin/docker build -f "$APP_RELEASE/deploy/resource-index/linux/Dockerfile" -t "$IMAGE" "$APP_RELEASE"
image_os=$(/usr/bin/docker image inspect "$IMAGE" --format '{{.Os}}')
image_arch=$(/usr/bin/docker image inspect "$IMAGE" --format '{{.Architecture}}')
[[ "$image_os/$image_arch" == "linux/amd64" ]] || { echo "finalizer image is not native linux/amd64: $image_os/$image_arch" >&2; exit 2; }
/usr/bin/docker run --rm --entrypoint python "$IMAGE" -c 'import boto3,bs4,cryptography,curl_cffi,PIL; from magnet.resource_index.pipeline.media_compute_finalize import finalize_compute_handoff; print("MEDIA_FINALIZER_IMPORTS_PASS")'

printf '%s\n' \
  "MEDIA_ALIYUN_FINALIZER_IMAGE_READY" \
  "image=$IMAGE" \
  "image_arch=$image_arch" \
  "image_os=$image_os" \
  "image_id=$(/usr/bin/docker image inspect "$IMAGE" --format '{{.Id}}')"
