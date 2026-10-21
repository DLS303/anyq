#!/usr/bin/env bash
# Backup and restore a synthetic database with a throwaway age key.
# Plaintext dumps and the private key stay in a temporary directory.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PG_BIN="/usr/lib/postgresql/16/bin"

if [ -f "$ROOT/deploy/.env" ]; then
  echo "anyq: refusing to run the round-trip while deploy/.env exists" >&2
  exit 1
fi

if [ ! -x "$PG_BIN/initdb" ]; then
  echo "anyq: PostgreSQL 16 server binaries are required for the local round-trip" >&2
  exit 1
fi

WORK=""
PGDATA=""
PG_STARTED=0
COMPOSE_STARTED=0
ANYQ_ENV_FILE=""
ANYQ_COMPOSE_FILE=""
ANYQ_COMPOSE_PROJECT=""

cleanup() {
  status=$?
  if [ "$PG_STARTED" -eq 1 ]; then
    "$PG_BIN/pg_ctl" -D "$PGDATA" stop -m immediate || true
    PG_STARTED=0
  fi
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

finish_case() {
  if [ "$PG_STARTED" -eq 1 ]; then
    "$PG_BIN/pg_ctl" -D "$PGDATA" stop -m immediate
    PG_STARTED=0
  fi
  if [ "$COMPOSE_STARTED" -eq 1 ]; then
    docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
      down -v --remove-orphans
    COMPOSE_STARTED=0
  fi
  rm -rf "$WORK"
  WORK=""
}

query() {
  local db="$1"
  local sql="$2"
  if [ "$BACKUP_RUNNER" = "local" ]; then
    psql --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname "$db" \
      --no-align --tuples-only --command "$sql"
  else
    docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
      exec -T postgres psql --username anyq --dbname "$db" \
      --no-align --tuples-only --command "$sql"
  fi
}

start_local() {
  PGDATA="$WORK/pgdata"
  mkdir -p "$WORK/sock" "$WORK/uploads"
  printf 'synthetic\n' > "$WORK/uploads/probe.txt"
  "$PG_BIN/initdb" -D "$PGDATA" --username=anyq --auth-local=trust --auth-host=trust \
    --encoding=UTF8 --locale=C.UTF-8 >/dev/null
  "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$WORK/pg.log" \
    -o "-p 54329 -k $WORK/sock -c listen_addresses=127.0.0.1" start >/dev/null
  PG_STARTED=1
  export PGHOST=127.0.0.1
  export PGPORT=54329
  export PGUSER=anyq
  export PGDATABASE=anyq
  unset PGPASSWORD || true
  export BACKUP_DATA_DIR="$WORK/uploads"
  for _ in $(seq 1 50); do
    if pg_isready -h 127.0.0.1 -p 54329 -U anyq -d postgres >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  psql --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname postgres \
    --set=ON_ERROR_STOP=1 --command 'CREATE DATABASE anyq' >/dev/null
  psql --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname anyq \
    --set=ON_ERROR_STOP=1 \
    --command "CREATE TABLE backup_probe (id integer PRIMARY KEY, label text NOT NULL); INSERT INTO backup_probe (id, label) VALUES (1, 'synthetic');" \
    >/dev/null
}

start_compose() {
  local pw volume
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
  unset BACKUP_DATA_DIR || true
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
  docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
    exec -T --user root postgres sh -c 'printf "synthetic\n" > /uploads/probe.txt'
  docker compose --env-file "$ANYQ_ENV_FILE" -f "$ANYQ_COMPOSE_FILE" -p "$ANYQ_COMPOSE_PROJECT" \
    exec -T postgres psql --username anyq --dbname anyq --set=ON_ERROR_STOP=1 \
    --command "CREATE TABLE backup_probe (id integer PRIMARY KEY, label text NOT NULL); INSERT INTO backup_probe (id, label) VALUES (1, 'synthetic');" \
    >/dev/null
}

run_roundtrip() {
  local mode="$1"
  local identity_path new_dump dump_name stamp tar_path label count
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
  export BACKUP_RUNNER="$mode"
  export BACKUP_DIR="$WORK/local"
  export BACKUP_RETENTION_DAYS=14
  export RCLONE_REMOTE_1=r1
  export RCLONE_REMOTE_2=r2
  export RCLONE_DEST_PATH=anyq
  export RCLONE_CONFIG_R1_TYPE=alias
  export RCLONE_CONFIG_R1_REMOTE="$WORK/r1"
  export RCLONE_CONFIG_R2_TYPE=alias
  export RCLONE_CONFIG_R2_REMOTE="$WORK/r2"
  mkdir -p "$BACKUP_DIR" "$WORK/r1/anyq" "$WORK/r2/anyq"
  printf 'old\n' > "$BACKUP_DIR/anyq-postgres-20000101T000000Z.dump.age"
  printf 'keep\n' > "$BACKUP_DIR/anyq-postgres-20990101T000000Z.dump.age"
  touch -d '20 days ago' "$BACKUP_DIR/anyq-postgres-20000101T000000Z.dump.age"
  touch -d '1 day ago' "$BACKUP_DIR/anyq-postgres-20990101T000000Z.dump.age"
  printf 'old\n' > "$WORK/r1/anyq/anyq-postgres-20000101T000000Z.dump.age"
  printf 'old\n' > "$WORK/r2/anyq/anyq-postgres-20000101T000000Z.dump.age"
  touch -d '20 days ago' "$WORK/r1/anyq/anyq-postgres-20000101T000000Z.dump.age"
  touch -d '20 days ago' "$WORK/r2/anyq/anyq-postgres-20000101T000000Z.dump.age"

  if [ "$mode" = "local" ]; then
    start_local
  else
    start_compose
  fi

  "$ROOT/deploy/backup.sh"

  if [ -e "$BACKUP_DIR/anyq-postgres-20000101T000000Z.dump.age" ]; then
    echo "anyq: old local dump was kept" >&2
    exit 1
  fi
  if [ ! -e "$BACKUP_DIR/anyq-postgres-20990101T000000Z.dump.age" ]; then
    echo "anyq: recent local dump was deleted" >&2
    exit 1
  fi
  if [ -e "$WORK/r1/anyq/anyq-postgres-20000101T000000Z.dump.age" ]; then
    echo "anyq: old remote dump was kept" >&2
    exit 1
  fi
  if compgen -G "$BACKUP_DIR/.partial-*" >/dev/null; then
    echo "anyq: plaintext partial left behind" >&2
    exit 1
  fi
  if compgen -G "$BACKUP_DIR/anyq-postgres-*.dump" >/dev/null; then
    echo "anyq: plaintext dump left behind" >&2
    exit 1
  fi

  new_dump="$(find "$BACKUP_DIR" -type f -name 'anyq-postgres-*.dump.age' \
    ! -name 'anyq-postgres-20990101T000000Z.dump.age' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
  if [ -z "$new_dump" ]; then
    echo "anyq: encrypted dump was not written" >&2
    exit 1
  fi
  dump_name="$(basename "$new_dump")"
  stamp="${dump_name#anyq-postgres-}"
  stamp="${stamp%.dump.age}"
  tar_path="$WORK/r1/anyq/anyq-data-${stamp}.tar.gz.age"
  cmp "$WORK/r1/anyq/$dump_name" "$WORK/r2/anyq/$dump_name"
  cmp "$tar_path" "$WORK/r2/anyq/anyq-data-${stamp}.tar.gz.age"
  if pg_restore -l "$WORK/r1/anyq/$dump_name" >/dev/null 2>&1; then
    echo "anyq: encrypted dump was readable as a database dump" >&2
    exit 1
  fi
  if grep -a -q 'synthetic' "$WORK/r1/anyq/$dump_name"; then
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

  if [ "$mode" = "local" ]; then
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
  fi

  finish_case
  if [ -e "$identity_path" ]; then
    echo "anyq: private key was left on disk" >&2
    exit 1
  fi
  echo "anyq: backup round-trip ok (${mode})"
}

run_roundtrip local

have_docker=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  have_docker=1
fi
if [ "$have_docker" -eq 1 ]; then
  run_roundtrip compose
fi
