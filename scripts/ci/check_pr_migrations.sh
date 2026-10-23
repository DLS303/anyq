#!/usr/bin/env bash
# Run the migration contract self-test, then check migration files added
# or modified relative to BASE_SHA.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$ROOT/scripts/ci/check_migrations.py" --self-test

base="${BASE_SHA:-}"
case "$base" in
  ""|0000000000000000000000000000000000000000) exit 0 ;;
esac

files=()
while IFS= read -r line; do
  if [ -n "$line" ]; then
    files+=("$line")
  fi
done < <(git -C "$ROOT" diff --name-only --diff-filter=AMR "${base}..HEAD" -- apps/api/alembic/versions)

if [ "${#files[@]}" -eq 0 ]; then
  exit 0
fi

cd "$ROOT"
python3 scripts/ci/check_migrations.py "${files[@]}"
