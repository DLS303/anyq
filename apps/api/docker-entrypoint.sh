#!/bin/sh
# Production start. The process stays root only long enough to prepare the
# data volume, then gunicorn runs as the unprivileged user anyq (uid 10001).
set -eu

fail() {
  echo "anyq-api: $1" >&2
  exit 1
}

if [ "${ANYQ_ENV:-}" != "production" ]; then
  fail "ANYQ_ENV must be production"
fi

secret="${JWT_SECRET:-${SUPERAPP_SECRET:-}}"
secret=$(printf '%s' "$secret" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

if [ -z "$secret" ]; then
  fail "JWT_SECRET is missing"
fi

if [ "${#secret}" -lt 32 ]; then
  fail "JWT_SECRET must be at least 32 characters"
fi

folded=$(printf '%s' "$secret" | tr '[:upper:]' '[:lower:]')
case "$folded" in
  *changeme*|*change-me*|*change_me*|*replace-me*|*replace_me*|*replace-with*|*your-secret*|*test-only*|*not-a-secret*|*placeholder*|*jwt-secret*|*jwt_secret*|*superapp*)
    fail "JWT_SECRET is a placeholder"
    ;;
esac

if [ -z "${CORS_ORIGINS:-}" ]; then
  fail "CORS_ORIGINS must be set"
fi

case "${CORS_ORIGINS}" in
  *\**)
    fail "CORS_ORIGINS must not contain a wildcard"
    ;;
esac

if [ -n "${ANYQ_DEMO_PASSWORD:-}" ]; then
  fail "ANYQ_DEMO_PASSWORD must be empty in production"
fi

case "${DATABASE_URL:-}" in
  *://superapp:superapp@*|*://anyq:anyq@*|*://postgres:postgres@*|*://user:password@*|*://anyq:changeme@*)
    fail "DATABASE_URL uses a default password"
    ;;
esac

# The JSON store lock is in-process. More than one worker can corrupt the file.
if [ "${WEB_CONCURRENCY:-1}" != "1" ]; then
  fail "WEB_CONCURRENCY must be 1 while data is stored in the JSON file"
fi

domain="${DOMAIN:-}"
if [ -n "$domain" ] && [ "$domain" != "localhost" ]; then
  case ",${CORS_ORIGINS}," in
    *",https://${domain},"*) ;;
    *) fail "CORS_ORIGINS must include https://${domain}" ;;
  esac
fi

mkdir -p /data/uploads /data/private /data/public
chown -R anyq:anyq /data

if [ "$#" -eq 0 ] || [ "${1:-}" = "gunicorn" ]; then
  set -- gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT:-8010}" \
    --workers 1 \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
    --keep-alive 5 \
    --max-requests "${GUNICORN_MAX_REQUESTS:-2000}" \
    --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-50}" \
    --access-logfile - \
    --error-logfile - \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
fi

exec gosu anyq "$@"
