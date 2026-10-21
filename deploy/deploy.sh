#!/usr/bin/env bash
# Pull, build, and start the production stack. On a failed health check or
# smoke request, tag the previous images back and start them again.
#
#   ./deploy/deploy.sh
#   DEPLOY_REF=main ./deploy/deploy.sh
#   DEPLOY_PULL=0 ./deploy/deploy.sh
#
# DEPLOY_PULL=0 skips git fetch. Use that only for a local build.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

lock_file="${ANYQ_DEPLOY_LOCK:-/tmp/anyq-deploy.lock}"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "anyq: another deploy is already running" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/deploy/check_env.sh"
load_env "$ROOT/deploy/.env"
validate_env
chmod 600 "$ROOT/deploy/.env" || true

API_CONTAINER="${ANYQ_API_CONTAINER:-anyq-api}"
export ANYQ_API_CONTAINER="$API_CONTAINER"

if [ "${DEPLOY_PULL:-1}" != "0" ]; then
  if [ ! -d "$ROOT/.git" ]; then
    echo "anyq: $ROOT is not a git checkout" >&2
    exit 1
  fi
  ref="${DEPLOY_REF:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)}"
  if [ "$ref" = "HEAD" ]; then
    echo "anyq: checkout is detached. Set DEPLOY_REF." >&2
    exit 1
  fi
  case "$ref" in
    *[!A-Za-z0-9._/-]*)
      echo "anyq: unsupported DEPLOY_REF" >&2
      exit 1
      ;;
  esac
  git -C "$ROOT" fetch --prune origin "$ref"
  git -C "$ROOT" checkout "$ref"
  git -C "$ROOT" merge --ff-only "origin/$ref"
fi

COMPOSE=(docker compose --env-file "$ROOT/deploy/.env" -f "$ROOT/deploy/docker-compose.prod.yml")

snapshot_if_healthy() {
  local container="$1"
  local image="$2"
  local status
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container" 2>/dev/null || echo missing)"
  if [ "$status" = "healthy" ] && docker image inspect "${image}:current" >/dev/null 2>&1; then
    docker tag "${image}:current" "${image}:rollback"
    echo "anyq: saved ${image}:rollback"
  fi
}

wait_healthy() {
  local attempt status container
  for attempt in $(seq 1 48); do
    local ready=1
    for container in "$API_CONTAINER" anyq-web anyq-caddy; do
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container" 2>/dev/null || echo missing)"
      if [ "$status" != "healthy" ]; then
        ready=0
      fi
      if [ "$status" = "unhealthy" ]; then
        echo "anyq: $container is unhealthy" >&2
        return 1
      fi
    done
    if [ "$ready" -eq 1 ]; then
      return 0
    fi
    sleep 5
  done
  echo "anyq: timed out waiting for healthy containers" >&2
  return 1
}

smoke() {
  local base curl_opts
  base="https://${DOMAIN}"
  curl_opts=(-fsS --compressed --retry 8 --retry-delay 2 --retry-connrefused --max-time 20)
  if [ "$DOMAIN" = "localhost" ]; then
    curl_opts+=(-k)
  fi
  curl "${curl_opts[@]}" "$base/healthz" | grep -q '"ok":true'
  curl "${curl_opts[@]}" "$base/health" | grep -q '"ok":true'
  curl "${curl_opts[@]}" "$base/v1/version" | grep -q '"version"'
  docker exec "$API_CONTAINER" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8010/v1/health/ready', timeout=6).read().decode())" | grep -q '"ok":true'
  curl "${curl_opts[@]}" "$base/v1/modules" | grep -q '"ok":true'
  curl "${curl_opts[@]}" -o /dev/null "$base/ru"
}

show_logs() {
  "${COMPOSE[@]}" logs --tail 80 || true
}

rollback() {
  local restored=0 name
  for name in anyq-api anyq-web; do
    if docker image inspect "${name}:rollback" >/dev/null 2>&1; then
      docker tag "${name}:rollback" "${name}:current"
      restored=1
      echo "anyq: restored ${name}:current from ${name}:rollback"
    fi
  done
  if [ "$restored" -ne 1 ]; then
    echo "anyq: no rollback image is available" >&2
    return 1
  fi
  "${COMPOSE[@]}" up -d --no-build --remove-orphans
  wait_healthy
}

snapshot_if_healthy "$API_CONTAINER" anyq-api
snapshot_if_healthy anyq-web anyq-web

if [ -z "${GIT_SHA:-}" ]; then
  GIT_SHA="$(git -C "$ROOT" rev-parse --short=7 HEAD 2>/dev/null || true)"
  export GIT_SHA
fi
if [ -z "${BUILD_TIME:-}" ]; then
  BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export BUILD_TIME
fi

echo "anyq: building images"
"${COMPOSE[@]}" build

echo "anyq: starting containers"
"${COMPOSE[@]}" up -d --remove-orphans

if ! wait_healthy || ! smoke; then
  show_logs
  echo "anyq: deploy failed, rolling back" >&2
  if ! rollback; then
    exit 1
  fi
  echo "anyq: rollback finished. The previous images are running." >&2
  exit 1
fi

echo "anyq: deploy finished. https://${DOMAIN} is responding."
