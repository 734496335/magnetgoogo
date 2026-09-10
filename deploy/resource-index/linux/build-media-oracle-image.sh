#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DEFAULT_APP_RELEASE=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
APP_RELEASE=${APP_RELEASE:-$DEFAULT_APP_RELEASE}
release_name=$(basename "$APP_RELEASE")
if [[ ! "$release_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "release directory name is not safe for a Docker tag: $release_name" >&2
  exit 2
fi
IMAGE=${MAGNET_MEDIA_IMAGE:-magnet-media-daily:oracle-shadow-$release_name}
PYTHON_IMAGE=${MAGNET_MEDIA_PYTHON_IMAGE:-python:3.11.9-slim-bookworm}
PIP_INDEX_URL=${MAGNET_MEDIA_PIP_INDEX_URL:-https://pypi.org/simple}

if [[ ! -d "$APP_RELEASE" ]]; then
  echo "APP_RELEASE must point to an existing media release" >&2
  exit 2
fi
if [[ ! -f "$APP_RELEASE/deploy/resource-index/linux/Dockerfile" ]]; then
  echo "APP_RELEASE does not contain the media Dockerfile" >&2
  exit 2
fi
if [[ ! "$IMAGE" =~ ^[A-Za-z0-9._/@:-]+$ ]]; then
  echo "MAGNET_MEDIA_IMAGE contains unsupported characters" >&2
  exit 2
fi
if [[ $(uname -m) != "aarch64" ]]; then
  echo "Oracle media image must be built on native aarch64" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 2
fi

docker build \
  --pull \
  --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE" \
  --build-arg "PIP_INDEX_URL=$PIP_INDEX_URL" \
  -f "$APP_RELEASE/deploy/resource-index/linux/Dockerfile" \
  -t "$IMAGE" \
  "$APP_RELEASE"

image_arch=$(docker image inspect "$IMAGE" --format '{{.Architecture}}')
image_os=$(docker image inspect "$IMAGE" --format '{{.Os}}')
image_id=$(docker image inspect "$IMAGE" --format '{{.Id}}')
if [[ "$image_arch" != "arm64" || "$image_os" != "linux" ]]; then
  echo "Oracle media image is not native linux/arm64: $image_os/$image_arch" >&2
  exit 2
fi

docker run --rm --entrypoint python "$IMAGE" -c 'import boto3,bs4,cryptography,curl_cffi,PIL; print("MEDIA_ARM64_IMPORTS_PASS")'
docker run --rm --entrypoint sh "$IMAGE" -c 'command -v ssh >/dev/null && command -v scp >/dev/null && echo MEDIA_SSH_CLIENT_PASS'

printf '%s\n' \
  "MEDIA_ORACLE_IMAGE_READY" \
  "image=$IMAGE" \
  "image_arch=$image_arch" \
  "image_os=$image_os" \
  "image_id=$image_id"
