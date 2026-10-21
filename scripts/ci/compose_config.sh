#!/usr/bin/env bash
# Render the production compose file with a generated env file.
# The file is removed afterwards. Values are not printed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="$ROOT/deploy/.env"
created=0

cleanup() {
  status=$?
  if [ "$created" -eq 1 ]; then
    rm -f "$env_file"
  fi
  exit "$status"
}
trap cleanup EXIT

if [ ! -e "$env_file" ]; then
  created=1
  pw="$(openssl rand -hex 24)"
  jwt="$(openssl rand -hex 32)"
  hash="$(openssl rand -hex 32)"
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::add-mask::$pw"
    echo "::add-mask::$jwt"
    echo "::add-mask::$hash"
  fi
  umask 077
  cat > "$env_file" <<EOF
ANYQ_ENV=production
JWT_SECRET=${jwt}
LOGIN_HASH_SECRET=${hash}
CORS_ORIGINS=http://localhost
POSTGRES_PASSWORD=${pw}
DATABASE_URL=postgresql+psycopg://anyq:${pw}@postgres:5432/anyq
ANYQ_DEMO_PASSWORD=
DOMAIN=localhost
ACME_EMAIL=ci@localhost
INTERNAL_API_URL=http://api:8010
NEXT_PUBLIC_PILOT_MODE=1
WEB_CONCURRENCY=2
BACKUP_RETENTION_DAYS=14
EOF
fi

docker compose --env-file "$env_file" -f "$ROOT/deploy/docker-compose.prod.yml" config >/dev/null
echo "compose config: ok"
