#!/usr/bin/env bash
# Hourly backup: pg_dump -Fc and the uploads archive, encrypted with age,
# then copied to two rclone remotes.
# Retention is per class: hourly 48 hours, 7 daily, 4 weekly, 6 monthly.
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
mkdir -p "$backup_dir/hourly" "$backup_dir/daily" "$backup_dir/weekly" "$backup_dir/monthly"
plain_dump="$backup_dir/.partial-${stamp}.dump"
plain_tar="$backup_dir/.partial-${stamp}.tar.gz"
enc_dump="$backup_dir/hourly/anyq-postgres-${stamp}.dump.age"
enc_tar="$backup_dir/hourly/anyq-data-${stamp}.tar.gz.age"
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

stamp_of() {
  local base="${1##*/}"
  case "$base" in
    anyq-postgres-*.dump.age)
      base="${base#anyq-postgres-}"
      base="${base%.dump.age}"
      ;;
    anyq-data-*.tar.gz.age)
      base="${base#anyq-data-}"
      base="${base%.tar.gz.age}"
      ;;
    *)
      return 1
      ;;
  esac
  case "$base" in
    [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
    *)
      return 1
      ;;
  esac
  printf '%s' "$base"
}

period_of() {
  local kind="$1" stamp="$2"
  local day="${stamp:0:8}"
  case "$kind" in
    daily) printf '%s' "$day" ;;
    monthly) printf '%s' "${stamp:0:6}" ;;
    weekly) date -u -d "$day" +%G-W%V ;;
    *) return 1 ;;
  esac
}

# Print basenames that fall outside this class. hourly is handled by age.
class_drop_list() {
  local kind="$1" keep="$2"
  shift 2
  local -a names=("$@")
  local -A best_stamp=()
  local name stamp period n=0 line
  local -A keep_period=()
  local -a drop=()
  if [ "$#" -eq 0 ]; then
    return 0
  fi
  for name in "${names[@]}"; do
    stamp="$(stamp_of "$name")" || continue
    period="$(period_of "$kind" "$stamp")" || continue
    if [ -z "${best_stamp[$period]:-}" ] || [[ "$stamp" > "${best_stamp[$period]}" ]]; then
      best_stamp[$period]="$stamp"
    fi
  done
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    n=$((n + 1))
    if [ "$n" -le "$keep" ]; then
      keep_period["${line#* }"]=1
    fi
  done < <(
    for period in "${!best_stamp[@]}"; do
      printf '%s %s\n' "${best_stamp[$period]}" "$period"
    done | sort -r
  )
  for name in "${names[@]}"; do
    stamp="$(stamp_of "$name")" || continue
    period="$(period_of "$kind" "$stamp")" || continue
    if [ -z "${keep_period[$period]:-}" ] || [ "$stamp" != "${best_stamp[$period]}" ]; then
      drop+=("$name")
    fi
  done
  if [ "${#drop[@]}" -gt 0 ]; then
    printf '%s\n' "${drop[@]}"
  fi
}

list_class_files() {
  local dir="$1"
  if [ ! -d "$dir" ]; then
    return 0
  fi
  find "$dir" -maxdepth 1 -type f \
    \( -name 'anyq-postgres-*.dump.age' -o -name 'anyq-data-*.tar.gz.age' \) \
    -printf '%f\n'
}

prune_local_hourly() {
  local dir="$1"
  if [ ! -d "$dir" ]; then
    return 0
  fi
  find "$dir" -maxdepth 1 -type f \
    \( -name 'anyq-postgres-*.dump.age' -o -name 'anyq-data-*.tar.gz.age' \) \
    -mmin +$((48 * 60)) -delete
}

prune_local_counted() {
  local dir="$1" kind="$2" keep="$3"
  local -a names=()
  local name
  mapfile -t names < <(list_class_files "$dir")
  if [ "${#names[@]}" -eq 0 ]; then
    return 0
  fi
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    rm -f "$dir/$name"
  done < <(class_drop_list "$kind" "$keep" "${names[@]}")
}

prune_local() {
  local root="$1"
  prune_local_hourly "$root/hourly"
  prune_local_counted "$root/daily" daily 7
  prune_local_counted "$root/weekly" weekly 4
  prune_local_counted "$root/monthly" monthly 6
  find "$root" -maxdepth 1 -type f \
    \( -name 'anyq-postgres-*.dump.age' -o -name 'anyq-postgres-*.sql.gz' \
       -o -name 'anyq-postgres-*.dump' -o -name 'anyq-data-*.tar.gz.age' \
       -o -name 'anyq-data-*.tar.gz' \) \
    -mmin +$((48 * 60)) -delete
}

prune_remote_hourly() {
  local remote="$1"
  rc delete "${remote}:${dest}/hourly" --min-age 48h \
    --include "anyq-postgres-*.dump.age" \
    --include "anyq-data-*.tar.gz.age"
}

prune_remote_counted() {
  local remote="$1" class="$2" kind="$3" keep="$4"
  local -a names=()
  local name
  mapfile -t names < <(rc lsf "${remote}:${dest}/${class}" --files-only \
    --include "anyq-postgres-*.dump.age" \
    --include "anyq-data-*.tar.gz.age" || true)
  if [ "${#names[@]}" -eq 0 ]; then
    return 0
  fi
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    rc deletefile "${remote}:${dest}/${class}/${name}"
  done < <(class_drop_list "$kind" "$keep" "${names[@]}")
}

prune_remote() {
  local remote="$1"
  prune_remote_hourly "$remote"
  prune_remote_counted "$remote" daily daily 7
  prune_remote_counted "$remote" weekly weekly 4
  prune_remote_counted "$remote" monthly monthly 6
  rc delete "${remote}:${dest}" --max-depth 1 --min-age 48h \
    --include "anyq-postgres-*.dump.age" \
    --include "anyq-postgres-*.sql.gz" \
    --include "anyq-data-*.tar.gz.age" \
    --include "anyq-data-*.tar.gz"
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

publish_class() {
  local remote="$1" class="$2" file="$3"
  rc copyto "$file" "${remote}:${dest}/${class}/$(basename "$file")"
}

dump_database "$plain_dump"
archive_uploads "$plain_tar"
encrypt "$plain_dump" "$enc_dump"
encrypt "$plain_tar" "$enc_tar"
test -s "$enc_dump"
test -s "$enc_tar"
cp -p "$enc_dump" "$backup_dir/daily/"
cp -p "$enc_tar" "$backup_dir/daily/"
cp -p "$enc_dump" "$backup_dir/weekly/"
cp -p "$enc_tar" "$backup_dir/weekly/"
cp -p "$enc_dump" "$backup_dir/monthly/"
cp -p "$enc_tar" "$backup_dir/monthly/"
prune_local "$backup_dir"

for remote in "$RCLONE_REMOTE_1" "$RCLONE_REMOTE_2"; do
  for class in hourly daily weekly monthly; do
    publish_class "$remote" "$class" "$backup_dir/$class/$(basename "$enc_dump")"
    publish_class "$remote" "$class" "$backup_dir/$class/$(basename "$enc_tar")"
  done
  prune_remote "$remote"
done

echo "anyq: wrote $enc_dump"
echo "anyq: wrote $enc_tar"
