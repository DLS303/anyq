#!/usr/bin/env bash
# Hourly backup: pg_dump -Fc and the uploads archive, encrypted with age,
# then copied to two rclone remotes. Retention is BACKUP_RETENTION_DAYS (14).
#
# The server has the age public key only. The private key stays offline.
# Remote names and the public key come from the environment. See deploy/.env.production.example.
#
# Restore into a scratch database with deploy/restore.sh.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT/deploy/check_env.sh"
if [ -f "$ROOT/deploy/.env" ]; then
  load_env "$ROOT/deploy/.env"
fi

umask 077

require_name() {
  local label="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[A-Za-z][A-Za-z0-9_-]{0,63}$ ]]; then
    echo "anyq: ${label} must be an rclone remote name configured on the server" >&2
    exit 1
  fi
}

runner="${BACKUP_RUNNER:-compose}"
case "$runner" in
  compose|local) ;;
  *)
    echo "anyq: BACKUP_RUNNER must be compose or local" >&2
    exit 1
    ;;
esac

retention="${BACKUP_RETENTION_DAYS:-14}"
case "$retention" in
  ''|*[!0-9]*|0)
    echo "anyq: BACKUP_RETENTION_DAYS must be a positive number" >&2
    exit 1
    ;;
esac

case "${AGE_RECIPIENT:-}" in
  age1*) ;;
  "ssh-ed25519 "*|"ssh-rsa "*) ;;
  *)
    echo "anyq: AGE_RECIPIENT must be an age public key" >&2
    exit 1
    ;;
esac

require_name "RCLONE_REMOTE_1" "${RCLONE_REMOTE_1:-}"
require_name "RCLONE_REMOTE_2" "${RCLONE_REMOTE_2:-}"
if [ "$RCLONE_REMOTE_1" = "$RCLONE_REMOTE_2" ]; then
  echo "anyq: the two backup remotes must be different" >&2
  exit 1
fi

dest="${RCLONE_DEST_PATH:-anyq}"
case "$dest" in
  ""|.*|*..*|*[!A-Za-z0-9_./-]*)
    echo "anyq: RCLONE_DEST_PATH is empty or has unsupported characters" >&2
    exit 1
    ;;
esac

backup_dir="${BACKUP_DIR:-/var/backups/anyq}"
mkdir -p "$backup_dir"
exec 9>"$backup_dir/.lock"
if ! flock -n 9; then
  echo "anyq: backup already running" >&2
  exit 0
fi

partials=()
cleanup() {
  status=$?
  local f
  for f in "${partials[@]+"${partials[@]}"}"; do
    rm -f "$f"
  done
  exit "$status"
}
trap cleanup EXIT

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
plain_dump="$backup_dir/.partial-${stamp}.dump"
plain_tar="$backup_dir/.partial-${stamp}.tar.gz"
enc_dump="$backup_dir/anyq-postgres-${stamp}.dump.age"
enc_tar="$backup_dir/anyq-data-${stamp}.tar.gz.age"
data_volume="${BACKUP_DATA_VOLUME:-anyq-data}"

compose() {
  local env_file="${ANYQ_ENV_FILE:-$ROOT/deploy/.env}"
  local file="${ANYQ_COMPOSE_FILE:-$ROOT/deploy/docker-compose.prod.yml}"
  local project="${ANYQ_COMPOSE_PROJECT:-anyq}"
  docker compose --env-file "$env_file" -f "$file" -p "$project" "$@"
}

rc() {
  rclone --quiet "$@"
}

encrypt() {
  local src="$1"
  local dest_file="$2"
  if ! age -r "$AGE_RECIPIENT" -o "$dest_file" "$src"; then
    rm -f "$dest_file"
    return 1
  fi
  rm -f "$src"
}

dump_database() {
  local dest_file="$1"
  partials+=("$dest_file")
  if [ "$runner" = "local" ]; then
    : "${PGHOST:?anyq: PGHOST is required}"
    : "${PGUSER:?anyq: PGUSER is required}"
    : "${PGDATABASE:?anyq: PGDATABASE is required}"
    pg_dump -Fc --no-owner --no-privileges \
      --host "$PGHOST" --port "${PGPORT:-5432}" \
      --username "$PGUSER" --dbname "$PGDATABASE" \
      --file "$dest_file"
  else
    compose exec -T postgres \
      pg_dump -Fc --username anyq --dbname anyq --no-owner --no-privileges \
      > "$dest_file"
  fi
}

archive_uploads() {
  local dest_file="$1"
  partials+=("$dest_file")
  if [ "$runner" = "local" ]; then
    if [ -z "${BACKUP_DATA_DIR:-}" ] || [ ! -d "$BACKUP_DATA_DIR" ]; then
      echo "anyq: BACKUP_DATA_DIR must be a directory" >&2
      exit 1
    fi
    tar -C "$BACKUP_DATA_DIR" -czf "$dest_file" .
  else
    docker run --rm --user "$(id -u):$(id -g)" \
      -v "${data_volume}:/data:ro" \
      -v "${backup_dir}:/backup" \
      alpine:3.20 \
      tar -C /data -czf "/backup/$(basename "$dest_file")" .
  fi
}

copy_one() {
  local remote="$1"
  local file="$2"
  rc copyto "$file" "${remote}:${dest}/$(basename "$file")"
  rc delete "${remote}:${dest}" --min-age "${retention}d" \
    --include "anyq-postgres-*.dump.age" \
    --include "anyq-data-*.tar.gz.age"
}

dump_database "$plain_dump"
archive_uploads "$plain_tar"
encrypt "$plain_dump" "$enc_dump"
encrypt "$plain_tar" "$enc_tar"
test -s "$enc_dump"
test -s "$enc_tar"
copy_one "$RCLONE_REMOTE_1" "$enc_dump"
copy_one "$RCLONE_REMOTE_1" "$enc_tar"
copy_one "$RCLONE_REMOTE_2" "$enc_dump"
copy_one "$RCLONE_REMOTE_2" "$enc_tar"

find "$backup_dir" -type f \
  \( -name 'anyq-data-*.tar.gz' -o -name 'anyq-data-*.tar.gz.age' \
     -o -name 'anyq-postgres-*.sql.gz' -o -name 'anyq-postgres-*.dump' \
     -o -name 'anyq-postgres-*.dump.age' \) \
  -mtime +"$retention" -delete

echo "anyq: wrote $enc_dump"
echo "anyq: wrote $enc_tar"
