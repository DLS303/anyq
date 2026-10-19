#!/usr/bin/env bash
# Archive uploads and media, and dump PostgreSQL with pg_dump.
#
#   ./deploy/backup.sh
#
# Restore (replace STAMP with the archive name):
#   docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml stop api
#   docker run --rm \
#     -v anyq-data:/data \
#     -v /var/backups/anyq:/backup:ro \
#     alpine:3.20 \
#     sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -C /data -xzf /backup/anyq-data-STAMP.tar.gz'
#   gunzip -c /var/backups/anyq/anyq-postgres-STAMP.sql.gz \
#     | docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml exec -T postgres \
#       psql --username anyq --dbname anyq
#   docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml up -d
#
# Keep the archives on this server, or on another disk in Kazakhstan.
# Do not send them to storage outside the country.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT/deploy/check_env.sh"
if [ -f "$ROOT/deploy/.env" ]; then
  load_env "$ROOT/deploy/.env"
fi

backup_dir="${BACKUP_DIR:-/var/backups/anyq}"
retention="${BACKUP_RETENTION_DAYS:-14}"
case "$retention" in
  ''|*[!0-9]*|0)
    echo "anyq: BACKUP_RETENTION_DAYS must be a positive number" >&2
    exit 1
    ;;
esac

mkdir -p "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$backup_dir/anyq-data-$stamp.tar.gz"

# Write the archive as the invoking user so retention can delete it later.
# File ownership inside the archive stays whatever is on the volume.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v anyq-data:/data:ro \
  -v "$backup_dir":/backup \
  alpine:3.20 \
  tar -C /data -czf "/backup/anyq-data-$stamp.tar.gz" .

dump="$backup_dir/anyq-postgres-$stamp.sql.gz"
docker compose --env-file "$ROOT/deploy/.env" -f "$ROOT/deploy/docker-compose.prod.yml" exec -T postgres \
  pg_dump --username anyq --dbname anyq --no-owner --no-privileges | gzip > "$dump"

find "$backup_dir" -type f \( -name 'anyq-data-*.tar.gz' -o -name 'anyq-postgres-*.sql.gz' \) -mtime +"$retention" -delete
echo "anyq: wrote $archive"
echo "anyq: wrote $dump"
