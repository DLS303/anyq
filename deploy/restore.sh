#!/usr/bin/env bash
# Restore one encrypted pg_dump into a new database.
#
#   deploy/restore.sh --remote <rclone-remote> [--stamp YYYYmmddTHHMMSSZ] [--scratch-db anyq_restore]
#
# Steps: rclone copy, age -d, pg_restore. The scratch database is not the live database.
# AGE_IDENTITY_FILE is the private key path. It must sit outside this repository.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT/deploy/check_env.sh"
if [ -f "$ROOT/deploy/.env" ]; then
  load_env "$ROOT/deploy/.env"
fi

umask 077

usage() {
  echo "usage: deploy/restore.sh --remote NAME [--stamp YYYYmmddTHHMMSSZ] [--scratch-db NAME]" >&2
}

remote=""
stamp=""
scratch="anyq_restore"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --remote)
      remote="${2:-}"
      shift 2
      ;;
    --stamp)
      stamp="${2:-}"
      shift 2
      ;;
    --scratch-db)
      scratch="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ ! "$remote" =~ ^[A-Za-z][A-Za-z0-9_-]{0,63}$ ]]; then
  echo "anyq: --remote must be an rclone remote name" >&2
  exit 1
fi

case "$stamp" in
  ""|[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
  *)
    echo "anyq: --stamp must be YYYYmmddTHHMMSSZ" >&2
    exit 1
    ;;
esac

case "$scratch" in
  [A-Za-z_][A-Za-z0-9_]*) ;;
  *)
    echo "anyq: scratch database name is not an identifier" >&2
    exit 1
    ;;
esac
if [ "${#scratch}" -gt 63 ]; then
  echo "anyq: scratch database name is too long" >&2
  exit 1
fi
case "$scratch" in
  anyq|postgres|template0|template1)
    echo "anyq: refusing to restore into ${scratch}" >&2
    exit 1
    ;;
esac
if [ -n "${PGDATABASE:-}" ] && [ "$scratch" = "$PGDATABASE" ]; then
  echo "anyq: refusing to restore into the source database" >&2
  exit 1
fi

if [ -z "${AGE_IDENTITY_FILE:-}" ] || [ ! -f "$AGE_IDENTITY_FILE" ]; then
  echo "anyq: AGE_IDENTITY_FILE is missing or not a file" >&2
  exit 1
fi
identity="$(readlink -f "$AGE_IDENTITY_FILE")"
repo="$(readlink -f "$ROOT")"
case "$identity" in
  "$repo"|"$repo"/*)
    echo "anyq: AGE_IDENTITY_FILE must not be inside the repository" >&2
    exit 1
    ;;
esac
perm="$(stat -c '%a' "$identity")"
others="${perm: -1}"
if [ "$others" != "0" ]; then
  echo "anyq: AGE_IDENTITY_FILE must not be readable by others" >&2
  exit 1
fi

dest="${RCLONE_DEST_PATH:-anyq}"
case "$dest" in
  ""|.*|*..*|*[!A-Za-z0-9_./-]*)
    echo "anyq: RCLONE_DEST_PATH is empty or has unsupported characters" >&2
    exit 1
    ;;
esac

runner="${BACKUP_RUNNER:-compose}"
case "$runner" in
  compose|local) ;;
  *)
    echo "anyq: BACKUP_RUNNER must be compose or local" >&2
    exit 1
    ;;
esac

work="$(mktemp -d)"
chmod 700 "$work"
cleanup() {
  status=$?
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT

rc() {
  rclone --quiet "$@"
}

list="$(rc lsf "${remote}:${dest}" --recursive --files-only --include 'anyq-postgres-*.dump.age')"
object=""
newest=""
while IFS= read -r line; do
  [ -z "$line" ] && continue
  line="${line//$'\r'/}"
  base="$(basename "$line")"
  case "$base" in
    anyq-postgres-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.dump.age) ;;
    *) continue ;;
  esac
  case "$line" in
    hourly/"$base"|daily/"$base"|weekly/"$base"|monthly/"$base") ;;
    *) continue ;;
  esac
  if [ -n "$stamp" ] && [ "$base" != "anyq-postgres-${stamp}.dump.age" ]; then
    continue
  fi
  if [ -z "$newest" ] || [[ "$base" > "$newest" ]]; then
    newest="$base"
    object="$line"
  fi
done <<< "$list"
case "$object" in
  hourly/*|daily/*|weekly/*|monthly/*) ;;
  *)
    echo "anyq: no encrypted dump on the remote" >&2
    exit 1
    ;;
esac

rc copyto "${remote}:${dest}/${object}" "$work/$object"
age -d -i "$identity" -o "$work/dump" "$work/$object"

compose() {
  local env_file="${ANYQ_ENV_FILE:-$ROOT/deploy/.env}"
  local file="${ANYQ_COMPOSE_FILE:-$ROOT/deploy/docker-compose.prod.yml}"
  local project="${ANYQ_COMPOSE_PROJECT:-anyq}"
  docker compose --env-file "$env_file" -f "$file" -p "$project" "$@"
}

psql_exec() {
  local db="$1"
  local sql="$2"
  if [ "$runner" = "local" ]; then
    psql --host "$PGHOST" --port "${PGPORT:-5432}" --username "$PGUSER" \
      --dbname "$db" --set=ON_ERROR_STOP=1 --no-align --tuples-only \
      --command "$sql"
  else
    compose exec -T postgres \
      psql --username anyq --dbname "$db" --set=ON_ERROR_STOP=1 \
      --no-align --tuples-only --command "$sql"
  fi
}

if [ "$runner" = "local" ]; then
  : "${PGHOST:?anyq: PGHOST is required}"
  : "${PGUSER:?anyq: PGUSER is required}"
  : "${PGDATABASE:?anyq: PGDATABASE is required}"
  admin_db="$PGDATABASE"
else
  admin_db="anyq"
fi

exists="$(psql_exec "$admin_db" "SELECT 1 FROM pg_database WHERE datname = '${scratch}'")"
exists="$(printf '%s' "$exists" | tr -d '[:space:]')"
if [ "$exists" = "1" ]; then
  echo "anyq: database ${scratch} already exists" >&2
  exit 1
fi
psql_exec "$admin_db" "CREATE DATABASE ${scratch}"

if [ "$runner" = "local" ]; then
  pg_restore --no-owner --no-privileges --exit-on-error \
    --host "$PGHOST" --port "${PGPORT:-5432}" --username "$PGUSER" \
    --dbname "$scratch" "$work/dump"
else
  compose exec -T postgres \
    pg_restore --no-owner --no-privileges --exit-on-error \
    --username anyq --dbname "$scratch" < "$work/dump"
fi

echo "anyq: restored ${object} into database ${scratch}"
echo "anyq: remove the private key from this machine when the restore is finished"
