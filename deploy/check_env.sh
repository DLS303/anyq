#!/usr/bin/env bash
# Validate deploy/.env before compose up. Safe to execute or to source.
# Keep the secret rules aligned with apps/api/docker-entrypoint.sh.

load_env() {
  local file="$1"
  local line key val
  if [ ! -f "$file" ]; then
    echo "anyq: missing environment file: $file" >&2
    echo "anyq: copy deploy/.env.production.example to deploy/.env" >&2
    return 1
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    case "$line" in
      *\`*|*'$(*)')
        echo "anyq: refusing command substitution in $file" >&2
        return 1
        ;;
    esac
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in
      [A-Za-z_][A-Za-z0-9_]*) ;;
      *)
        echo "anyq: bad key in $file: $key" >&2
        return 1
        ;;
    esac
    case "$val" in
      \"*\")
        val="${val#\"}"
        val="${val%\"}"
        ;;
      \'*\')
        val="${val#\'}"
        val="${val%\'}"
        ;;
    esac
    export "$key=$val"
  done < "$file"
}

validate_env() {
  local secret folded domain
  if [ "${ANYQ_ENV:-}" != "production" ]; then
    echo "anyq: ANYQ_ENV must be production" >&2
    return 1
  fi

  secret="${JWT_SECRET:-${SUPERAPP_SECRET:-}}"
  secret="${secret#"${secret%%[![:space:]]*}"}"
  secret="${secret%"${secret##*[![:space:]]}"}"
  if [ -z "$secret" ]; then
    echo "anyq: JWT_SECRET is missing" >&2
    return 1
  fi
  if [ "${#secret}" -lt 32 ]; then
    echo "anyq: JWT_SECRET must be at least 32 characters" >&2
    return 1
  fi
  folded="$(printf '%s' "$secret" | tr '[:upper:]' '[:lower:]')"
  case "$folded" in
    *changeme*|*change-me*|*change_me*|*replace-me*|*replace_me*|*replace-with*|*your-secret*|*test-only*|*not-a-secret*|*placeholder*|*jwt-secret*|*jwt_secret*|*superapp*)
      echo "anyq: JWT_SECRET is a placeholder" >&2
      return 1
      ;;
  esac

  if [ -z "${CORS_ORIGINS:-}" ]; then
    echo "anyq: CORS_ORIGINS must be set" >&2
    return 1
  fi
  case "${CORS_ORIGINS}" in
    *\**)
      echo "anyq: CORS_ORIGINS must not contain a wildcard" >&2
      return 1
      ;;
  esac

  if [ -n "${ANYQ_DEMO_PASSWORD:-}" ]; then
    echo "anyq: ANYQ_DEMO_PASSWORD must be empty in production" >&2
    return 1
  fi

  case "${DATABASE_URL:-}" in
    *://superapp:superapp@*|*://anyq:anyq@*|*://postgres:postgres@*|*://user:password@*|*://anyq:changeme@*)
      echo "anyq: DATABASE_URL uses a default password" >&2
      return 1
      ;;
  esac

  case "${POSTGRES_PASSWORD:-}" in
    anyq|postgres|superapp|changeme|password|secret)
      echo "anyq: POSTGRES_PASSWORD is a default" >&2
      return 1
      ;;
  esac

  case "${DATABASE_URL:-}" in
    postgresql://*|postgresql+psycopg://*|postgres://*) ;;
    *)
      echo "anyq: DATABASE_URL must be a PostgreSQL URL" >&2
      return 1
      ;;
  esac

  if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "anyq: POSTGRES_PASSWORD is missing" >&2
    return 1
  fi

  workers="${WEB_CONCURRENCY:-2}"
  case "$workers" in
    ''|*[!0-9]*)
      echo "anyq: WEB_CONCURRENCY must be a number from 1 to 8" >&2
      return 1
      ;;
  esac
  if [ "$workers" -lt 1 ] || [ "$workers" -gt 8 ]; then
    echo "anyq: WEB_CONCURRENCY must be a number from 1 to 8" >&2
    return 1
  fi

  domain="${DOMAIN:-}"
  case "$domain" in
    ""|*[!A-Za-z0-9.-]*|.*|*.|*..*)
      echo "anyq: DOMAIN must be a bare hostname" >&2
      return 1
      ;;
  esac
  if [ "$domain" != "localhost" ]; then
    case ",${CORS_ORIGINS}," in
      *",https://${domain},"*) ;;
      *)
        echo "anyq: CORS_ORIGINS must include https://${domain}" >&2
        return 1
        ;;
    esac
    case "${ACME_EMAIL:-}" in
      *@*.*) ;;
      *)
        echo "anyq: ACME_EMAIL must be an email address" >&2
        return 1
        ;;
    esac
  else
    case "${ACME_EMAIL:-}" in
      *@*.*|*@localhost) ;;
      *)
        echo "anyq: ACME_EMAIL must be an email address" >&2
        return 1
        ;;
    esac
    echo "anyq: DOMAIN=localhost uses a local certificate, not a public one." >&2
  fi

  case "${INTERNAL_API_URL:-}" in
    http://api:8010) ;;
    *)
      echo "anyq: INTERNAL_API_URL must be http://api:8010 for this compose file" >&2
      return 1
      ;;
  esac

  case "${NEXT_PUBLIC_PILOT_MODE:-1}" in
    0|1) ;;
    *)
      echo "anyq: NEXT_PUBLIC_PILOT_MODE must be 0 or 1" >&2
      return 1
      ;;
  esac

  case "${BACKUP_RETENTION_DAYS:-14}" in
    ''|*[!0-9]*)
      echo "anyq: BACKUP_RETENTION_DAYS must be a positive number of days" >&2
      return 1
      ;;
    0)
      echo "anyq: BACKUP_RETENTION_DAYS must be a positive number of days" >&2
      return 1
      ;;
  esac
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -euo pipefail
  root="$(cd "$(dirname "$0")" && pwd)"
  load_env "${1:-$root/.env}"
  validate_env
  echo "Environment file is valid."
fi
