#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run as root on the Aliyun media host" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
USER_NAME=${USER_NAME:-magnetmedia}
MEDIA_ROOT=${MEDIA_ROOT:-/var/lib/magnet-media/public}
HELPER_SOURCE=${HELPER_SOURCE:-$SCRIPT_DIR/../remote-static-mirror.py}
HELPER_TARGET=${HELPER_TARGET:-/usr/local/libexec/magnet-media-remote-static-mirror.py}
DEPLOY_PUBLIC_KEY_FILE=${DEPLOY_PUBLIC_KEY_FILE:-}
ORACLE_SOURCE_IP=${ORACLE_SOURCE_IP:-}

if [[ "$USER_NAME" != "magnetmedia" ]]; then
  echo "USER_NAME must remain magnetmedia" >&2
  exit 2
fi
if [[ "$MEDIA_ROOT" != "/var/lib/magnet-media/public" ]]; then
  echo "MEDIA_ROOT must remain /var/lib/magnet-media/public" >&2
  exit 2
fi
if [[ "$HELPER_TARGET" != "/usr/local/libexec/magnet-media-remote-static-mirror.py" ]]; then
  echo "HELPER_TARGET must remain the fixed root-owned helper path" >&2
  exit 2
fi
if [[ -z "$DEPLOY_PUBLIC_KEY_FILE" || ! -f "$DEPLOY_PUBLIC_KEY_FILE" ]]; then
  echo "DEPLOY_PUBLIC_KEY_FILE must point to the Oracle media deploy public key" >&2
  exit 2
fi
if [[ -z "$ORACLE_SOURCE_IP" || ! "$ORACLE_SOURCE_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "ORACLE_SOURCE_IP must be an IPv4 address" >&2
  exit 2
fi
if [[ ! -d "$MEDIA_ROOT/v1" || ! -f "$MEDIA_ROOT/v1/current.json" ]]; then
  echo "the live Aliyun media mirror root is missing its current control plane" >&2
  exit 2
fi
if [[ ! -f "$HELPER_SOURCE" ]]; then
  echo "remote static mirror helper source is missing" >&2
  exit 2
fi
for required in python3 ssh-keygen setfacl getfacl runuser; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "required command is missing: $required" >&2
    exit 2
  fi
done

mapfile -t public_key_lines < <(grep -Ev '^[[:space:]]*$' "$DEPLOY_PUBLIC_KEY_FILE")
if [[ ${#public_key_lines[@]} -ne 1 || ! "${public_key_lines[0]}" =~ ^ssh-ed25519[[:space:]]+[A-Za-z0-9+/=]+([[:space:]].*)?$ ]]; then
  echo "deploy public key must contain exactly one Ed25519 public key" >&2
  exit 2
fi
ssh-keygen -l -f "$DEPLOY_PUBLIC_KEY_FILE" >/dev/null

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/magnet-media-deploy --shell /bin/bash "$USER_NAME"
fi
if [[ "$(getent passwd "$USER_NAME" | cut -d: -f6)" != "/var/lib/magnet-media-deploy" ]]; then
  echo "existing magnetmedia user has an unexpected home directory" >&2
  exit 2
fi
if [[ "$(getent passwd "$USER_NAME" | cut -d: -f7)" != "/bin/bash" ]]; then
  echo "existing magnetmedia user has an unexpected login shell" >&2
  exit 2
fi
passwd -l "$USER_NAME" >/dev/null 2>&1 || true
if id -nG "$USER_NAME" | tr ' ' '\n' | grep -Eq '^(sudo|wheel)$'; then
  echo "magnetmedia must not be a sudo/wheel member" >&2
  exit 2
fi

home_dir=/var/lib/magnet-media-deploy
install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" "$home_dir/.ssh"
authorized_keys="$home_dir/.ssh/authorized_keys"
printf 'from="%s",restrict %s\n' "$ORACLE_SOURCE_IP" "${public_key_lines[0]}" > "$authorized_keys"
chown "$USER_NAME:$USER_NAME" "$authorized_keys"
chmod 0600 "$authorized_keys"

install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$HELPER_SOURCE" "$HELPER_TARGET"
helper_sha=$(sha256sum "$HELPER_TARGET" | awk '{print $1}')

setfacl -R -m "u:$USER_NAME:rwX" "$MEDIA_ROOT"
while IFS= read -r -d '' directory; do
  setfacl -m "d:u:$USER_NAME:rwx" "$directory"
done < <(find "$MEDIA_ROOT" -type d -print0)

if ! getfacl -cp "$MEDIA_ROOT" | grep -Eq "^user:$USER_NAME:rwx$"; then
  echo "media root ACL does not grant the deploy user rwx" >&2
  exit 2
fi
if ! getfacl -cp "$MEDIA_ROOT" | grep -Eq "^default:user:$USER_NAME:rwx$"; then
  echo "media root default ACL is missing" >&2
  exit 2
fi

health_output=$(runuser -u "$USER_NAME" -- python3 "$HELPER_TARGET" healthcheck --root "$MEDIA_ROOT")
if ! grep -Fq '"status": "pass"' <<<"$health_output"; then
  echo "magnetmedia helper healthcheck failed" >&2
  exit 2
fi

printf '%s\n' \
  "ALIYUN_MEDIA_MIRROR_USER_READY" \
  "user=$USER_NAME" \
  "media_root=$MEDIA_ROOT" \
  "helper=$HELPER_TARGET" \
  "helper_sha256=$helper_sha" \
  "source_ip=$ORACLE_SOURCE_IP" \
  "sudo_access=none" \
  "nginx=untouched" \
  "systemd=untouched"
