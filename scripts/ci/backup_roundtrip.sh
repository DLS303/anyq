#!/usr/bin/env bash
# Backup and restore a synthetic database with a throwaway age key.
# The database is postgis/postgis:16-3.4 with ICU. Plaintext and the private key stay in a temp directory.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [ -f "$ROOT/deploy/.env" ]; then
  echo "anyq: refusing to run the round-trip while deploy/.env exists" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "anyq: docker is required for the postgis round-trip" >&2
  exit 1
fi

locale="$(grep -E '^[A-Za-z][A-Za-z0-9_.@-]*$' "$ROOT/deploy/postgres-icu-locale" | tail -n 1 || true)"
if [ "$locale" != "ru-KZ" ]; then
  echo "anyq: deploy/postgres-icu-locale must be ru-KZ" >&2
  exit 1
fi
for compose_file in "$ROOT/deploy/docker-compose.prod.yml" "$ROOT/scripts/ci/docker-compose.backup-test.yml"; do
  if ! grep -q 'image: postgis/postgis:16-3.4' "$compose_file"; then
    echo "anyq: ${compose_file} is not postgis/postgis:16-3.4" >&2
    exit 1
  fi
  if ! grep -q -- "--icu-locale=${locale}" "$compose_file"; then
    echo "anyq: ${compose_file} does not init with ${locale}" >&2
    exit 1
  fi
done
if grep -q 'postgres:16-alpine' "$ROOT/deploy/docker-compose.prod.yml"; then
  echo "anyq: production compose still uses postgres:16-alpine" >&2
  exit 1
fi

WORK=""
COMPOSE_STARTED=0
ANYQ_ENV_FILE=""
ANYQ_COMPOSE_FILE=""
ANYQ_COMPOSE_PROJECT=""

cleanup() {
  status=$?
  if [ "$COMPOSE_STARTED" -eq 1 ]; then
    docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
      down -v --remove-orphans || true
    COMPOSE_STARTED=0
  fi
  if [ -n "$WORK" ] && [ -d "$WORK" ]; then
    rm -rf "$WORK"
  fi
  exit "$status"
}
trap cleanup EXIT

query() {
  local db="$1"
  local sql="$2"
  docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
    exec -T postgres psql --username anyq --dbname "$db" \
    --no-align --tuples-only --command "$sql"
}

plant() {
  local path="$1"
  local when="$2"
  mkdir -p "$(dirname "$path")"
  printf 'old\n' > "$path"
  touch -d "$when" "$path"
}

require_gone() {
  local path="$1"
  if [ -e "$path" ]; then
    echo "anyq: expected removal of $path" >&2
    exit 1
  fi
}

require_kept() {
  local path="$1"
  if [ ! -e "$path" ]; then
    echo "anyq: expected to keep $path" >&2
    exit 1
  fi
}

WORK="$(mktemp -d)"
chmod 700 "$WORK"
identity_path="$WORK/identity"
if ! age-keygen -o "$identity_path" >"$WORK/age.out" 2>&1; then
  cat "$WORK/age.out" >&2
  exit 1
fi
rm -f "$WORK/age.out"
chmod 600 "$identity_path"
export AGE_IDENTITY_FILE="$identity_path"
AGE_RECIPIENT="$(age-keygen -y "$identity_path")"
export AGE_RECIPIENT
export BACKUP_RUNNER=compose
export BACKUP_DIR="$WORK/local"
export RCLONE_REMOTE_1=r1
export RCLONE_REMOTE_2=r2
export RCLONE_DEST_PATH=anyq
export RCLONE_CONFIG_R1_TYPE=alias
export RCLONE_CONFIG_R1_REMOTE="$WORK/r1"
export RCLONE_CONFIG_R2_TYPE=alias
export RCLONE_CONFIG_R2_REMOTE="$WORK/r2"
mkdir -p "$BACKUP_DIR" "$WORK/r1/anyq" "$WORK/r2/anyq"

plant "$BACKUP_DIR/hourly/anyq-postgres-20000101T000000Z.dump.age" "72 hours ago"
plant "$BACKUP_DIR/hourly/anyq-postgres-20200101T010000Z.dump.age" "1 hour ago"
plant "$WORK/r1/anyq/hourly/anyq-postgres-20000101T000000Z.dump.age" "72 hours ago"
plant "$WORK/r1/anyq/hourly/anyq-postgres-20200101T010000Z.dump.age" "1 hour ago"
plant "$WORK/r2/anyq/hourly/anyq-postgres-20000101T000000Z.dump.age" "72 hours ago"
day=1
while [ "$day" -le 8 ]; do
  stamp="$(printf '202001%02dT000000Z' "$day")"
  plant "$BACKUP_DIR/daily/anyq-postgres-${stamp}.dump.age" "40 days ago"
  plant "$WORK/r1/anyq/daily/anyq-postgres-${stamp}.dump.age" "40 days ago"
  day=$((day + 1))
done
for stamp in 20200302T000000Z 20200309T000000Z 20200316T000000Z 20200323T000000Z 20200330T000000Z; do
  plant "$BACKUP_DIR/weekly/anyq-postgres-${stamp}.dump.age" "40 days ago"
  plant "$WORK/r1/anyq/weekly/anyq-postgres-${stamp}.dump.age" "40 days ago"
done
month=1
while [ "$month" -le 7 ]; do
  stamp="$(printf '2020%02d15T000000Z' "$month")"
  plant "$BACKUP_DIR/monthly/anyq-postgres-${stamp}.dump.age" "40 days ago"
  plant "$WORK/r1/anyq/monthly/anyq-postgres-${stamp}.dump.age" "40 days ago"
  month=$((month + 1))
done

pw="$(openssl rand -hex 24)"
volume="anyqbkci${RANDOM}-uploads"
ANYQ_COMPOSE_PROJECT="anyqbkci${RANDOM}"
ANYQ_COMPOSE_FILE="$ROOT/scripts/ci/docker-compose.backup-test.yml"
ANYQ_ENV_FILE="$WORK/pg.env"
umask 077
cat > "$ANYQ_ENV_FILE" <<EOF
POSTGRES_PASSWORD=${pw}
BACKUP_VOLUME_NAME=${volume}
EOF
export ANYQ_ENV_FILE ANYQ_COMPOSE_FILE ANYQ_COMPOSE_PROJECT
export BACKUP_DATA_VOLUME="$volume"
COMPOSE_STARTED=1
docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" up -d
ready=0
for _ in $(seq 1 60); do
  if docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
    exec -T postgres pg_isready -U anyq -d anyq >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "anyq: backup test postgres did not become ready" >&2
  exit 1
fi
locale_row="$(query anyq "SELECT datlocprovider::text || ' ' || COALESCE(daticulocale, '') FROM pg_database WHERE datname = 'anyq'")"
locale_row="$(printf '%s' "$locale_row" | tr -d '[:space:]')"
if [ "$locale_row" != "iru-KZ" ]; then
  echo "anyq: database locale is ${locale_row}, expected ICU ru-KZ" >&2
  exit 1
fi
docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
  exec -T --user root postgres sh -c 'printf "synthetic\n" > /uploads/probe.txt'
docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
  exec -T postgres psql --username anyq --dbname anyq --set=ON_ERROR_STOP=1 \
  --command "CREATE TABLE backup_probe (id integer PRIMARY KEY, label text NOT NULL); INSERT INTO backup_probe (id, label) VALUES (1, 'synthetic');" \
  >/dev/null

"$ROOT/deploy/backup.sh"

require_gone "$BACKUP_DIR/hourly/anyq-postgres-20000101T000000Z.dump.age"
require_kept "$BACKUP_DIR/hourly/anyq-postgres-20200101T010000Z.dump.age"
require_gone "$WORK/r1/anyq/hourly/anyq-postgres-20000101T000000Z.dump.age"
require_kept "$WORK/r1/anyq/hourly/anyq-postgres-20200101T010000Z.dump.age"
require_gone "$WORK/r2/anyq/hourly/anyq-postgres-20000101T000000Z.dump.age"
require_gone "$BACKUP_DIR/daily/anyq-postgres-20200101T000000Z.dump.age"
require_gone "$BACKUP_DIR/daily/anyq-postgres-20200102T000000Z.dump.age"
require_kept "$BACKUP_DIR/daily/anyq-postgres-20200108T000000Z.dump.age"
require_gone "$WORK/r1/anyq/daily/anyq-postgres-20200101T000000Z.dump.age"
require_kept "$WORK/r1/anyq/daily/anyq-postgres-20200108T000000Z.dump.age"
require_gone "$BACKUP_DIR/weekly/anyq-postgres-20200302T000000Z.dump.age"
require_gone "$BACKUP_DIR/weekly/anyq-postgres-20200309T000000Z.dump.age"
require_kept "$BACKUP_DIR/weekly/anyq-postgres-20200330T000000Z.dump.age"
require_gone "$WORK/r1/anyq/weekly/anyq-postgres-20200302T000000Z.dump.age"
require_kept "$WORK/r1/anyq/weekly/anyq-postgres-20200330T000000Z.dump.age"
require_gone "$BACKUP_DIR/monthly/anyq-postgres-20200115T000000Z.dump.age"
require_gone "$BACKUP_DIR/monthly/anyq-postgres-20200215T000000Z.dump.age"
require_kept "$BACKUP_DIR/monthly/anyq-postgres-20200715T000000Z.dump.age"
require_gone "$WORK/r1/anyq/monthly/anyq-postgres-20200115T000000Z.dump.age"
require_kept "$WORK/r1/anyq/monthly/anyq-postgres-20200715T000000Z.dump.age"
if compgen -G "$BACKUP_DIR/.partial-*" >/dev/null; then
  echo "anyq: plaintext partial left behind" >&2
  exit 1
fi

new_dump="$(find "$BACKUP_DIR/hourly" -type f -name 'anyq-postgres-*.dump.age' -mmin -30 -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
if [ -z "$new_dump" ]; then
  echo "anyq: encrypted dump was not written" >&2
  exit 1
fi
dump_name="$(basename "$new_dump")"
stamp="${dump_name#anyq-postgres-}"
stamp="${stamp%.dump.age}"
for class in hourly daily weekly monthly; do
  require_kept "$BACKUP_DIR/$class/$dump_name"
  require_kept "$WORK/r1/anyq/$class/$dump_name"
  require_kept "$WORK/r2/anyq/$class/$dump_name"
  cmp "$WORK/r1/anyq/$class/$dump_name" "$WORK/r2/anyq/$class/$dump_name"
done
tar_name="anyq-data-${stamp}.tar.gz.age"
tar_path="$WORK/r1/anyq/hourly/$tar_name"
cmp "$tar_path" "$WORK/r2/anyq/hourly/$tar_name"
if [ "$(head -c 5 "$WORK/r1/anyq/hourly/$dump_name")" = "PGDMP" ]; then
  echo "anyq: encrypted dump was a plaintext database dump" >&2
  exit 1
fi
if grep -a -q 'synthetic' "$WORK/r1/anyq/hourly/$dump_name"; then
  echo "anyq: synthetic label was present in the encrypted dump" >&2
  exit 1
fi

"$ROOT/deploy/restore.sh" --remote "$RCLONE_REMOTE_1" --scratch-db anyq_restore_ci
label="$(query anyq_restore_ci "SELECT label FROM backup_probe")"
count="$(query anyq_restore_ci "SELECT count(*) FROM backup_probe")"
if [ "$label" != "synthetic" ] || [ "$count" != "1" ]; then
  echo "anyq: scratch database did not contain the synthetic row" >&2
  exit 1
fi
count="$(query anyq "SELECT count(*) FROM backup_probe")"
if [ "$count" != "1" ]; then
  echo "anyq: source database changed during restore" >&2
  exit 1
fi

age -d -i "$identity_path" -o "$WORK/uploads.tar.gz" "$tar_path"
mkdir -p "$WORK/untar"
tar -xzf "$WORK/uploads.tar.gz" -C "$WORK/untar"
if ! grep -q 'synthetic' "$WORK/untar/probe.txt"; then
  echo "anyq: uploads archive did not contain the probe file" >&2
  exit 1
fi
rm -f "$WORK/uploads.tar.gz"

set +e
RCLONE_REMOTE_2=notconfigured "$ROOT/deploy/backup.sh"
status=$?
set -e
if [ "$status" -eq 0 ]; then
  echo "anyq: a missing second remote was accepted" >&2
  exit 1
fi
if compgen -G "$BACKUP_DIR/.partial-*" >/dev/null; then
  echo "anyq: plaintext partial left behind after a failed upload" >&2
  exit 1
fi

docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
  down -v --remove-orphans
COMPOSE_STARTED=0
rm -rf "$WORK"
saved_identity="$identity_path"
WORK=""
if [ -e "$saved_identity" ]; then
  echo "anyq: private key was left on disk" >&2
  exit 1
fi
echo "anyq: backup round-trip ok (postgis icu)"
