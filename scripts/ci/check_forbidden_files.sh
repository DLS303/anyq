#!/usr/bin/env bash
# Fail when git tracks data JSON, database files, env files, or key material.
# *.example and *.example.json are allowed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

is_forbidden() {
  local path="$1"
  local base lower
  base="${path##*/}"
  lower="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    .env*)
      case "$lower" in
        *.example) return 1 ;;
      esac
      return 0
      ;;
  esac
  case "$lower" in
    *.sqlite|*.db|*.pem|*.key|*.jks|*.keystore) return 0 ;;
  esac
  case "$path" in
    data/*.json)
      case "$lower" in
        *.example.json) return 1 ;;
      esac
      return 0
      ;;
  esac
  return 1
}

scan_repo() {
  local repo="$1"
  local path failed=0
  while IFS= read -r -d '' path; do
    if is_forbidden "$path"; then
      echo "forbidden tracked file: $path" >&2
      failed=1
    fi
  done < <(git -C "$repo" ls-files -z)
  return "$failed"
}

self_test() {
  local tmp repo
  tmp="$(mktemp -d)"
  repo="$tmp/repo"
  mkdir -p "$repo/data" "$repo/deploy"
  git -C "$repo" init -q
  printf '{}\n' > "$repo/data/test.json"
  printf '{}\n' > "$repo/data/db.example.json"
  printf 'x\n' > "$repo/.env"
  printf 'x\n' > "$repo/.env.example"
  printf 'x\n' > "$repo/deploy/.env.production.example"
  printf 'x\n' > "$repo/local.sqlite"
  printf 'x\n' > "$repo/notes.txt"
  git -C "$repo" add data/test.json
  if scan_repo "$repo"; then
    echo "self-test: data/test.json was accepted" >&2
    rm -rf "$tmp"
    return 1
  fi
  git -C "$repo" rm -q --cached data/test.json >/dev/null
  rm -f "$repo/data/test.json"
  git -C "$repo" add data/db.example.json .env.example deploy/.env.production.example notes.txt
  if ! scan_repo "$repo"; then
    echo "self-test: example files were rejected" >&2
    rm -rf "$tmp"
    return 1
  fi
  git -C "$repo" add .env local.sqlite
  if scan_repo "$repo"; then
    echo "self-test: .env or sqlite was accepted" >&2
    rm -rf "$tmp"
    return 1
  fi
  rm -rf "$tmp"
  echo "forbidden-files self-test: ok"
}

case "${1:-}" in
  --self-test) self_test ;;
  --root)
    scan_repo "$2"
    ;;
  "")
    scan_repo "$ROOT"
    ;;
  *)
    echo "usage: check_forbidden_files.sh [--self-test|--root DIR]" >&2
    exit 1
    ;;
esac
