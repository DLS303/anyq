#!/bin/sh
# Binds the standalone server on all interfaces. Docker sets HOSTNAME to the
# container id, which would make Next.js listen on that name only.
set -eu

url="${INTERNAL_API_URL:-}"
if [ -z "$url" ]; then
  echo "anyq-web: INTERNAL_API_URL is required" >&2
  exit 1
fi

case "$url" in
  *127.0.0.1*|*localhost*|*0.0.0.0*)
    echo "anyq-web: INTERNAL_API_URL must be the in-network API address" >&2
    exit 1
    ;;
esac

if [ ! -f /app/apps/web/server.js ]; then
  echo "anyq-web: standalone server is missing at /app/apps/web/server.js" >&2
  exit 1
fi

export HOSTNAME=0.0.0.0
export PORT="${PORT:-3000}"
cd /app
exec node apps/web/server.js
