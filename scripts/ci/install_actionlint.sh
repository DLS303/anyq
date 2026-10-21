#!/usr/bin/env bash
# Install a pinned actionlint binary into /usr/local/bin.

set -euo pipefail

version="${ACTIONLINT_VERSION:-1.7.7}"
if command -v actionlint >/dev/null 2>&1; then
  exit 0
fi

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp"
}
trap cleanup EXIT

curl -fsSL -o "$tmp/actionlint.tar.gz" \
  "https://github.com/rhysd/actionlint/releases/download/v${version}/actionlint_${version}_linux_amd64.tar.gz"
tar -xzf "$tmp/actionlint.tar.gz" -C "$tmp" actionlint
if [ "$(id -u)" -eq 0 ]; then
  install -m 0755 "$tmp/actionlint" /usr/local/bin/actionlint
else
  sudo install -m 0755 "$tmp/actionlint" /usr/local/bin/actionlint
fi
