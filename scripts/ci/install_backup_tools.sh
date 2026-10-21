#!/usr/bin/env bash
# Install age and rclone. Used by the server bootstrap and by CI.

set -euo pipefail

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

export DEBIAN_FRONTEND=noninteractive
as_root apt-get update
as_root apt-get install -y rclone

if apt-cache show age >/dev/null 2>&1; then
  as_root apt-get install -y age
  exit 0
fi

version="${AGE_VERSION:-1.2.1}"
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64) age_arch="amd64" ;;
  arm64) age_arch="arm64" ;;
  *)
    echo "anyq: unsupported architecture for age: $arch" >&2
    exit 1
    ;;
esac

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp"
}
trap cleanup EXIT

curl -fsSL -o "$tmp/age.tar.gz" \
  "https://github.com/FiloSottile/age/releases/download/v${version}/age-v${version}-linux-${age_arch}.tar.gz"
tar -xzf "$tmp/age.tar.gz" -C "$tmp"
as_root install -m 0755 "$tmp/age/age" /usr/local/bin/age
as_root install -m 0755 "$tmp/age/age-keygen" /usr/local/bin/age-keygen
