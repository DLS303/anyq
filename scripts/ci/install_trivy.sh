#!/usr/bin/env bash
# Install a pinned trivy binary into /usr/local/bin.

set -euo pipefail

version="${TRIVY_VERSION:-0.76.1}"
if command -v trivy >/dev/null 2>&1; then
  exit 0
fi

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp"
}
trap cleanup EXIT

curl -fsSL -o "$tmp/trivy.tar.gz" \
  "https://github.com/aquasecurity/trivy/releases/download/v${version}/trivy_${version}_Linux-64bit.tar.gz"
# From trivy_0.76.1_checksums.txt on the same release.
echo "c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0  $tmp/trivy.tar.gz" | sha256sum -c -
tar -xzf "$tmp/trivy.tar.gz" -C "$tmp" trivy
if [ "$(id -u)" -eq 0 ]; then
  install -m 0755 "$tmp/trivy" /usr/local/bin/trivy
else
  sudo install -m 0755 "$tmp/trivy" /usr/local/bin/trivy
fi
