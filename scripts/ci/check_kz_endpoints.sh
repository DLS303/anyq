#!/usr/bin/env bash
# Fail when a backup or object-storage endpoint under deploy/ is not listed
# in deploy/allowed_endpoints_kz.txt. Placeholders are not endpoints.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

strip_quotes() {
  local value="$1"
  case "$value" in
    \"*\") value="${value#\"}"; value="${value%\"}" ;;
    \'*\') value="${value#\'}"; value="${value%\'}" ;;
  esac
  printf '%s' "$value"
}

host_of() {
  local value="$1"
  value="${value#*://}"
  case "$value" in
    *@*) value="${value#*@}" ;;
  esac
  value="${value%%/*}"
  value="${value%%\?*}"
  value="${value%%:*}"
  printf '%s' "$value" | tr '[:upper:]' '[:lower:]'
}

load_allowlist() {
  ALLOWED=""
  local line host file="$1"
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ""|[[:space:]]\#*) continue ;;
    esac
    host="$(trim "$line" | tr '[:upper:]' '[:lower:]')"
    [ -n "$host" ] || continue
    ALLOWED="${ALLOWED}|${host}|"
  done < "$file"
}

host_allowed() {
  case "$ALLOWED" in
    *"|$1|"*) return 0 ;;
  esac
  return 1
}

key_is_endpoint() {
  case "$1" in
    *ENDPOINT*|*endpoint*|*[Ss]3*|*RCLONE*|*rclone*|*PGBACKREST*|*pgbackrest*|repo[12]*|REPO[12]*)
      return 0
      ;;
  esac
  return 1
}

skip_host() {
  case "$1" in
    ""|localhost|127.0.0.1|postgres|api|web|caddy) return 0 ;;
  esac
  return 1
}

check_host() {
  local host="$1" file="$2" key="$3"
  skip_host "$host" && return 0
  case "$host" in
    *.*) ;;
    *) return 0 ;;
  esac
  if host_allowed "$host"; then
    return 0
  fi
  echo "endpoint not in deploy/allowed_endpoints_kz.txt: ${file}: ${key}: ${host}" >&2
  return 1
}

check_value() {
  local value="$1" file="$2" key="$3"
  local url host failed=0
  value="$(strip_quotes "$(trim "$value")")"
  case "$value" in
    ""|"<set-on-server>") return 0 ;;
  esac
  case "$value" in
    postgresql://*|postgresql+*|postgres://*|redis://*) return 0 ;;
  esac
  local urls=""
  urls="$(printf '%s\n' "$value" | grep -oE '[a-zA-Z][a-zA-Z0-9+.-]*://[^[:space:]'\''"]+' || true)"
  if [ -n "$urls" ]; then
    while IFS= read -r url; do
      [ -n "$url" ] || continue
      case "$url" in
        postgresql://*|postgresql+*|postgres://*|redis://*) continue ;;
        s3://*|sftp://*|https://*|http://*) ;;
        *) continue ;;
      esac
      host="$(host_of "$url")"
      if ! check_host "$host" "$file" "$key"; then
        failed=1
      fi
    done <<EOF
$urls
EOF
    return "$failed"
  fi
  case "$value" in
    *.*)
      host="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
      check_host "$host" "$file" "$key"
      ;;
  esac
}

scan_tree() {
  local deploy="$1" allow="$2"
  local file line key value failed=0
  load_allowlist "$allow"
  while IFS= read -r file; do
    case "$file" in
      */allowed_endpoints_kz.txt) continue ;;
    esac
    # shellcheck disable=SC2094
    while IFS= read -r line || [ -n "$line" ]; do
      line="$(trim "$line")"
      case "$line" in
        ""|\#*) continue ;;
      esac
      case "$line" in
        *s3://*|*sftp://*)
          if ! check_value "$line" "$file" "line"; then
            failed=1
          fi
          ;;
      esac
      case "$line" in
        *=*) ;;
        *) continue ;;
      esac
      key="$(trim "${line%%=*}")"
      value="${line#*=}"
      if key_is_endpoint "$key"; then
        if ! check_value "$value" "$file" "$key"; then
          failed=1
        fi
      fi
    done < "$file"
  done < <(find "$deploy" -type f -print)
  return "$failed"
}

self_test() {
  local tmp deploy allow
  tmp="$(mktemp -d)"
  deploy="$tmp/deploy"
  allow="$deploy/allowed_endpoints_kz.txt"
  mkdir -p "$deploy"
  printf 'allowed.example.kz\n' > "$allow"
  {
    printf 'S3_ENDPOINT=https://allowed.example.kz/bucket\n'
    printf 'RCLONE_REMOTE_1=<set-on-server>\n'
    printf 'DATABASE_URL=postgresql+psycopg://postgres:5432/anyq\n'
    printf '# S3_ENDPOINT=https://comment.example.net\n'
  } > "$deploy/ok.env"
  if ! scan_tree "$deploy" "$allow"; then
    echo "self-test: allowed endpoint was rejected" >&2
    rm -rf "$tmp"
    return 1
  fi
  printf 'S3_ENDPOINT=https://other.example.net/bucket\n' > "$deploy/bad.env"
  if scan_tree "$deploy" "$allow"; then
    echo "self-test: foreign endpoint was accepted" >&2
    rm -rf "$tmp"
    return 1
  fi
  rm -rf "$tmp"
  echo "endpoint self-test: ok"
}

case "${1:-}" in
  --self-test) self_test ;;
  "")
    scan_tree "$ROOT/deploy" "$ROOT/deploy/allowed_endpoints_kz.txt"
    ;;
  *)
    echo "usage: check_kz_endpoints.sh [--self-test]" >&2
    exit 1
    ;;
esac
