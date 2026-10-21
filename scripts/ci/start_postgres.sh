#!/usr/bin/env bash
# Start an ephemeral PostgreSQL 16 container for CI.
# The password is generated here and masked. It is not stored in the workflow file.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [ -z "${GITHUB_ENV:-}" ]; then
  echo "anyq: this script writes DATABASE_URL to GITHUB_ENV" >&2
  exit 1
fi

locale="$(grep -E '^[A-Za-z][A-Za-z0-9_.@-]*$' "$ROOT/deploy/postgres-icu-locale" | tail -n 1 || true)"
if [ -z "$locale" ] || [ "$locale" = "TODO" ]; then
  echo "anyq: deploy/postgres-icu-locale has no locale token" >&2
  exit 1
fi

pw="$(openssl rand -hex 24)"
echo "::add-mask::$pw"

name="anyq-ci-postgres"
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" \
  -e POSTGRES_USER=anyq \
  -e POSTGRES_PASSWORD="$pw" \
  -e POSTGRES_DB=anyq \
  -e POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale-provider=icu --icu-locale=${locale}" \
  -p 127.0.0.1:5432:5432 \
  postgis/postgis:16-3.4 >/dev/null

ready=0
for _ in $(seq 1 60); do
  if docker exec "$name" pg_isready -U anyq -d anyq >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  docker logs "$name" >&2 || true
  echo "anyq: postgres did not become ready" >&2
  exit 1
fi

echo "DATABASE_URL=postgresql+psycopg://anyq:${pw}@127.0.0.1:5432/anyq" >> "$GITHUB_ENV"
echo "anyq: postgres is ready"
